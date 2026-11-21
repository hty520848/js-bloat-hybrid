'use strict';
// Calendar-sensitive archived tests use their authenticated source commit's
// timestamp. Monotonic performance clocks are unchanged.
// Keep package managers, builders and their completion timers on real time.
// Only the behavioral Mocha process uses the archived calendar fixture.
const apply=process.env.HYBRID_FIXED_CLOCK_APPLY==='1'||/(?:^|\/)_?mocha(?:\.js)?$/.test(process.argv[1]||'');
if(apply){
const ms=Number(process.env.HYBRID_FIXED_DATE_MS);if(!Number.isFinite(ms))throw Error('Missing fixed calendar timestamp');
const NativeDate=global.Date;
function FixedDate(...args){
 if(!new.target)return new NativeDate(ms).toString();
 return Reflect.construct(NativeDate,args.length?args:[ms],new.target===FixedDate?NativeDate:new.target);
}
Object.setPrototypeOf(FixedDate,NativeDate);FixedDate.prototype=NativeDate.prototype;FixedDate.now=()=>ms;global.Date=FixedDate;
}
