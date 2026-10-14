import json,re,subprocess,sys
src,out=sys.argv[1],sys.argv[2]
r=subprocess.run(['ffmpeg','-hide_banner','-i',src,'-af','loudnorm=I=-14:TP=-1.5:LRA=9:print_format=json','-f','null','-'],capture_output=True,text=True).stderr
d=json.loads(re.search(r'\{[^{}]+\}',r,re.S).group(0))
af=(f"loudnorm=I=-14:TP=-1.5:LRA=9:measured_I={d['input_i']}:measured_TP={d['input_tp']}:measured_LRA={d['input_lra']}"
    f":measured_thresh={d['input_thresh']}:offset={d['target_offset']},aresample=48000")
subprocess.run(['ffmpeg','-v','error','-y','-i',src,'-c:v','copy','-af',af,'-c:a','aac','-b:a','256k',out],check=True)
m=subprocess.run(['ffmpeg','-hide_banner','-i',out,'-af','ebur128=framelog=quiet:peak=true','-f','null','-'],capture_output=True,text=True).stderr
print(src,'->',out); print('\n'.join(l for l in m.splitlines() if re.search(r' I:|Peak:|LRA:',l)))
