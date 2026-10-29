"""Minimal trusted HTTPS-behind-reverse-proxy translator backend. Python 3.10+ stdlib."""
import os, json, base64, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = os.environ.get('OPENAI_API_KEY', '')
MODEL = os.environ.get('VISION_MODEL', 'gpt-4.1-mini')
HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', '8787'))
MAX_BODY = 2_500_000
PROMPT = '''You translate manga/manhwa into natural Vietnamese. The OCR blocks and their IDs are given, and a screenshot gives visual context. Group meaning within each block, keep each ID intact, do not split into words. Use speaker relationships and recent context for natural pronouns, but never invent dialogue. Exclude UI labels, watermarks, ads, chapter navigation, credits, sound effects when not speech, by setting include=false. Return a JSON object with a translations array; each item {id: integer, translation: string, include: boolean}. Include every input id exactly once. Do not return markdown. Do not include unsafe extra content not present in source.''' 
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  if self.path != '/translate': return self.reply(404, {'error':'not found'})
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=MAX_BODY: return self.reply(413,{'error':'request too large'})
   obj=json.loads(self.rfile.read(n))
   bubbles=obj.get('bubbles',[])
   if not isinstance(bubbles,list) or len(bubbles)>16: return self.reply(400,{'error':'invalid bubbles'})
   if not API_KEY: return self.reply(503,{'error':'server API key not configured'})
   image=obj.get('image_base64','')
   if not isinstance(image,str) or len(image)>2_000_000: return self.reply(400,{'error':'invalid image'})
   if image: base64.b64decode(image,validate=True)
   content=[{'type':'text','text':json.dumps({'bubbles':bubbles,'context':obj.get('context',[]),'language':obj.get('language','ja')},ensure_ascii=False)}]
   if image: content.append({'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+image,'detail':'low'}})
   payload={'model':MODEL,'temperature':0.2,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':PROMPT},{'role':'user','content':content}]}
   req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+API_KEY,'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=22) as resp: data=json.load(resp)
   parsed=json.loads(data['choices'][0]['message']['content'])
   translations=parsed.get('translations',[])
   if not isinstance(translations,list): raise ValueError('invalid response')
   allowed={b.get('id') for b in bubbles}
   cleaned=[]
   for t in translations:
    if isinstance(t,dict) and t.get('id') in allowed:
     cleaned.append({'id':t['id'],'translation':str(t.get('translation',''))[:1200],'include':bool(t.get('include',True))})
   return self.reply(200,{'translations':cleaned})
  except (ValueError,KeyError,TypeError) as e: return self.reply(400,{'error':str(e)})
  except Exception: return self.reply(502,{'error':'translation provider unavailable'})
 def reply(self,code,obj):
  payload=json.dumps(obj,ensure_ascii=False).encode('utf-8')
  self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
if __name__=='__main__':
 print(f'Listening on {HOST}:{PORT}. Use an HTTPS reverse proxy with authentication and rate limiting for remote access.')
 ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
