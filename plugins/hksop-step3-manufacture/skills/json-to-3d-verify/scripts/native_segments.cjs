'use strict';
const fs=require('node:fs'),path=require('node:path');
const [root,input]=process.argv.slice(2);
const api=require(path.join(root,'engine/design/design.cjs')),ctx=api.context();
const project=JSON.parse(fs.readFileSync(input,'utf8')),checked=api.inspectProject(project,ctx);
if(!checked.report.valid)throw Error(JSON.stringify(checked.report.issues));
const scene=ctx.R.sceneFor(checked.layout,checked.kits,checked.p.optical,[],ctx.E,ctx.catalog);
let session=ctx.E.createSession(scene,undefined,{pauseOnHeightErrors:true,maxSteps:256,maxSegments:2048,maxBranches:128});
let batch;do{batch=ctx.E.autoAdvance(session,{maxEvents:64,maxMilliseconds:800});session=batch.session;}while(batch.canContinue);
if(batch.issues.length)throw Error(JSON.stringify(batch.issues));
const point=(xyz,xy,h)=>xyz?[xyz.x,xyz.y,xyz.z]:[xy.x,xy.y,h];
const measured=session.segments.filter(s=>s.lengthMm>1e-6);
const segments=measured.map(s=>{
 const start=point(s.from3D,s.from,s.beam.axisHeightMm);
 const matches=measured.filter(p=>p!==s && p.sourceId===s.sourceId && Math.abs(p.pathEndMm-s.pathStartMm)<.002 &&
   Math.hypot(...point(p.to3D,p.to,p.beam.axisHeightMm).map((v,i)=>v-start[i]))<.002);
 const interactionIds=[...new Set([s.hitInstanceId,s.lensMediumId,s.assemblyId,
   ...(s.pathStartMm<.002?[s.sourceId]:matches.map(p=>p.hitInstanceId))].filter(Boolean))];
 const b=s.beam;return {id:s.id,interactionIds,source:s.sourceId,hit:s.hitInstanceId||null,branch:s.branchId,
 a:point(s.from3D,s.from,b.axisHeightMm),b:point(s.to3D,s.to,b.axisHeightMm),
 q:[b.q.re,b.q.im],qSagittal:b.qSagittal?[b.qSagittal.re,b.qSagittal.im]:[b.q.re,b.q.im],
 wavelengthNm:b.wavelengthNm,m2:b.beamQualityM2||1,index:b.mediumIndex||1,rangeMm:s.lengthMm};});
process.stdout.write(JSON.stringify({segments,catalogVersion:ctx.catalog.version}));
