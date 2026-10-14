import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require=createRequire('/Users/yusong/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/runtime.js');
const sharp=require('sharp');
const here=path.dirname(new URL(import.meta.url).pathname);
const old=path.resolve(here,'../thesis-revision-T129-2026-10-03/evidence');
const notes=JSON.parse(fs.readFileSync(path.join(old,'project-one-four-seed-notes.json'),'utf8'));
const sops=JSON.parse(fs.readFileSync(path.join(old,'historical-seven-sop.json'),'utf8'));
const out=path.join(here,'figures');fs.mkdirSync(out,{recursive:true});
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
function text(s,x,y,size=32,color='#111'){return `<text x="${x}" y="${y}" fill="${color}" font-size="${size}" font-weight="700" font-family="Songti SC, Times New Roman, serif" xml:space="preserve">${esc(s)}</text>`;}
function units(s){return [...s].reduce((a,c)=>a+(/[\u2e80-\uffef]/u.test(c)?1:0.54),0);}
function wrap(s,width=1160,size=32){let lines=[''];for(const c of s){let j=lines.length-1;if(units(lines[j]+c)*size>width){if(/[。；，！？、.,;!?）)]/u.test(c)){lines[j]+=c;continue;}const tail=lines[j].match(/(\d+\.?|[（(])$/u);if(tail){lines[j]=lines[j].slice(0,-tail[0].length);lines.push(tail[0]+c);}else{lines.push(c);}}else lines[j]+=c;}return lines;}
function block(s,y){const lines=wrap(s);return {svg:lines.map((x,i)=>text(x,56,y+i*44)).join(''),end:y+(lines.length-1)*44};}
const rows=[];
async function save(name,body,height,source){
 const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1320" height="${height}" viewBox="0 0 1320 ${height}"><rect width="1320" height="${height}" fill="#fff"/>${body}</svg>`;
 fs.writeFileSync(path.join(out,name+'.svg'),svg);
 await sharp(Buffer.from(svg)).png().toFile(path.join(out,name+'.png'));
 rows.push({media:`word/media/image${43+rows.length}.png`,svg:name+'.svg',png:name+'.png',width:1320,height,source});
}
for(const [i,n] of notes.entries()){
 let b=text(`项目一固定笔记样例 ${i+1}`,56,80,42)+'<line x1="56" y1="108" x2="1265" y2="108" stroke="#333" stroke-width="2"/>';
 b+=text('记录信息',56,165,34,'#19475d');
 b+=text('标题：'+n.title,56,224);
 b+=text('类型：'+n.experiment_type+'　日期：'+n.experiment_date,56,270);
 b+=text('结构化字段',56,333,34,'#19475d');let y=391;
 for(const [key,label] of [['reagents','试剂'],['instrument','仪器'],['sample','样本'],['result','结果']]){
  const item=block(label+'：'+n.fixed_fields[key],y);b+=item.svg;y=item.end+44;
 }
 y+=28;b+=text('正文原文',56,y,34,'#19475d');y+=60;
 for(const line of n.content_text.split('\n')){const item=block(line,y);b+=item.svg;y=item.end+44;}
 await save('project-one-note-'+(i+1),b,y+18,{title:n.title,fixed_fields:n.fixed_fields,content_text:n.content_text});
}
for(const [i,items] of [sops.slice(0,4),sops.slice(4)].entries()){
 let b=text(`项目一 SOP 提要样例（${i+1}/2）`,56,80,42)+'<line x1="56" y1="108" x2="1265" y2="108" stroke="#333" stroke-width="2"/>';let y=172;
 for(const item of items){
  b+=text(`F${item.file_id} / chunk ${item.chunk_id}  ${item.filename}`,56,y,31,'#19475d');y+=62;
  const entry=block(item.snippet,y);b+=entry.svg;y=entry.end+78;
 }
 await save('project-one-sop-'+(i+1),b,y-30,{records:items.map(x=>({file_id:x.file_id,chunk_id:x.chunk_id,filename:x.filename,snippet:x.snippet}))});
}
fs.writeFileSync(path.join(here,'figure-changes.json'),JSON.stringify({basis:'Rebuilt native SVG from preserved structured records; removed repeated disclaimer subtitle and audit footer.',figures:rows},null,2));
console.log('Rebuilt '+rows.length+' appendix figures from unchanged records.');
