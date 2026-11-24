import { useEffect, useLayoutEffect, useRef } from 'react';
import { type AuroraMix } from './aurora-mix';

/* Living background: one small fragment shader whose colours and pace follow the real
   energy mix of the house (solar amber, grid blue, battery pink, consumption green).
   Rendered at a third of the screen resolution and at most 30 fps, paused while the tab
   is hidden, drawn once under prefers-reduced-motion. No data is invented: without a live
   reading the scene rests on a calm neutral mix. */

const VERTEX = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
const FRAGMENT = `precision mediump float;
uniform vec2 u_res;uniform float u_time;uniform vec4 u_mix;uniform float u_energy;uniform float u_dark;
float hash(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),f.x),f.y);}
float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<4;i++){v+=a*noise(p);p=p*2.03+vec2(17.1,9.2);a*=.5;}return v;}
float glow(vec2 p,vec2 c,float r){vec2 d=p-c;return exp(-dot(d,d)/(r*r));}
void main(){
  vec2 p=(gl_FragCoord.xy-.5*u_res)/u_res.y;float ar=u_res.x/u_res.y;float t=u_time;
  vec2 q=vec2(fbm(p*1.1+vec2(0.,t*.05)),fbm(p*1.1+vec2(5.2,-t*.04)));
  vec2 r=vec2(fbm(p*1.5+2.*q+vec2(1.7,9.2)+t*.03),fbm(p*1.5+2.*q+vec2(8.3,2.8)-t*.026));
  float f=fbm(p*1.25+2.4*r);
  vec2 w=p+(r-.5)*.55;
  /* Sources sit where the flow diagram puts them: sun above, grid left, battery below, house right. */
  float s=glow(w,vec2(-.28*ar,.52),.62)*u_mix.x;
  float g=glow(w,vec2(-.52*ar,-.34),.58)*u_mix.y;
  float b=glow(w,vec2(.05*ar,-.58),.52)*u_mix.z;
  float l=glow(w,vec2(.46*ar,.08),.74)*u_mix.w;
  float band=smoothstep(.22,.82,f);
  vec3 cs=vec3(.98,.70,.22),cg=vec3(.22,.50,.98),cb=vec3(.93,.42,.72),cl=vec3(.16,.86,.62);
  vec3 light=cs*s+cg*g+cb*b+cl*l;
  float lift=.72+.28*u_energy;
  vec3 dark=vec3(.018,.028,.036)+light*(.17+.50*band)*lift+vec3(.02,.05,.05)*band*.5;
  float v=smoothstep(1.25,.25,length(p*vec2(.8,1.)));
  dark*=.62+.38*v;
  vec3 tint=(vec3(1.)-(cs*s+cg*g+cb*b+cl*l)/max(1.,s+g+b+l))*min(1.,s+g+b+l);
  vec3 day=vec3(.935,.948,.936)-tint*(.13+.27*band)*lift+vec3(.03)*band;
  vec3 col=mix(day,dark,u_dark);
  col+=(hash(gl_FragCoord.xy+fract(t)*91.7)-.5)*.012;
  gl_FragColor=vec4(col,1.);
}`;

export default function Aurora({ mix, dark }: { mix: AuroraMix; dark: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const target = useRef({ mix, dark });
  const redraw = useRef<() => void>(() => {});
  const snap = useRef<() => void>(() => {});
  target.current = { mix, dark };
  useEffect(() => { redraw.current(); }, [mix.solar, mix.grid, mix.battery, mix.load, mix.energy, dark]);
  // A theme change is drawn at once so the circular reveal captures the new sky.
  useLayoutEffect(() => { snap.current(); }, [dark]);
  useEffect(() => {
    const node = canvas.current;
    const gl = node?.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power' });
    if (!node || !gl) return; // CSS fallback gradient stays visible
    const compile = (type: number, source: string) => { const shader = gl.createShader(type)!; gl.shaderSource(shader, source); gl.compileShader(shader); return shader; };
    const program = gl.createProgram()!;
    gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAGMENT));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return;
    gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, 'p');
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    const uniform = (name: string) => gl.getUniformLocation(program, name);
    const uRes = uniform('u_res'), uTime = uniform('u_time'), uMix = uniform('u_mix'), uEnergy = uniform('u_energy'), uDark = uniform('u_dark');
    node.classList.add('ready');
    const still = window.matchMedia('(prefers-reduced-motion: reduce)');
    const now = { ...target.current.mix, dark: target.current.dark ? 1 : 0 };
    let frame = 0, last = 0, clock = 40, lost = false;
    const size = () => {
      const width = Math.max(160, Math.round(Math.min(innerWidth, 1920) / 3)), height = Math.max(120, Math.round(Math.min(innerHeight, 1400) / 3));
      if (node.width !== width || node.height !== height) { node.width = width; node.height = height; gl.viewport(0, 0, width, height); }
    };
    const draw = () => {
      gl.uniform2f(uRes, node.width, node.height);
      gl.uniform1f(uTime, clock);
      gl.uniform4f(uMix, now.solar, now.grid, now.battery, now.load);
      gl.uniform1f(uEnergy, now.energy);
      gl.uniform1f(uDark, now.dark);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };
    const settle = (rate: number) => {
      const goal = target.current;
      for (const key of ['solar', 'grid', 'battery', 'load', 'energy'] as const) now[key] += (goal.mix[key] - now[key]) * rate;
      now.dark += ((goal.dark ? 1 : 0) - now.dark) * Math.min(1, rate * 3);
    };
    const tick = (time: number) => {
      frame = requestAnimationFrame(tick);
      if (lost || time - last < 32) return; // ~30 fps is enough for slow light
      const delta = Math.min(0.1, (time - last) / 1000);
      last = time;
      settle(Math.min(1, delta * 1.6));
      clock += delta * (0.55 + 1.1 * now.energy);
      draw();
    };
    const run = () => {
      cancelAnimationFrame(frame);
      if (lost) return;
      size();
      if (still.matches || document.hidden) { settle(1); draw(); return; }
      last = performance.now();
      frame = requestAnimationFrame(tick);
    };
    redraw.current = () => { if (still.matches && !lost) { settle(1); draw(); } };
    snap.current = () => { now.dark = target.current.dark ? 1 : 0; if (!lost) draw(); };
    const onLost = (event: Event) => { event.preventDefault(); lost = true; cancelAnimationFrame(frame); node.classList.remove('ready'); };
    window.addEventListener('resize', run);
    document.addEventListener('visibilitychange', run);
    still.addEventListener('change', run);
    node.addEventListener('webglcontextlost', onLost);
    run();
    return () => {
      cancelAnimationFrame(frame);
      redraw.current = () => {};
      snap.current = () => {};
      window.removeEventListener('resize', run);
      document.removeEventListener('visibilitychange', run);
      still.removeEventListener('change', run);
      node.removeEventListener('webglcontextlost', onLost);
    };
  }, []);
  return <canvas ref={canvas} className="aurora" aria-hidden="true" />;
}
