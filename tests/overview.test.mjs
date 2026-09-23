import test from "node:test";
import assert from "node:assert/strict";
import {visibleYRange,windowLayout,attachOverview} from "../dashboard/overview.mjs";

const end=Date.parse("2026-09-14T16:00:00Z"), hour=3600000;
const trace=()=>({x:[end-48*hour,null,end-23*hour,end],y:[900,null,40,60]});

test("switching 7 days to 24 hours removes an older peak from the y scale and restores it on return",()=>{
  const week=windowLayout([trace()],168,end),day=windowLayout([trace()],24,end);
  assert.deepEqual(week["yaxis.range"],[0,1000]);
  assert.deepEqual(day["yaxis.range"],[0,65]);
  assert.deepEqual(day["xaxis.range"],[end-24*hour,end]);
  assert.equal(day["yaxis.autorange"],false);
  assert.deepEqual(windowLayout([trace()],168,end),week);
});

test("only visible hospitals set the scale; empty, zero, and negative readings have finite ranges",()=>{
  const hidden={x:[end],y:[5000],visible:"legendonly"};
  assert.deepEqual(visibleYRange([trace(),hidden],end-24*hour,end),[0,65]);
  hidden.visible=false;
  assert.deepEqual(visibleYRange([hidden],end-24*hour,end),[0,10]);
  assert.deepEqual(visibleYRange([{x:[end],y:[0]}],end-hour,end),[0,10]);
  const negative=visibleYRange([{x:[end-hour,end],y:[-20,-5]}],end-hour,end);
  assert.ok(negative[0]<-20 && negative[1]===0);
  assert.deepEqual(visibleYRange([{x:[end],y:[null]}],end-hour,end),[0,10]);
});

test("scale includes a line crossing the window edge without joining missing periods",()=>{
  const joined={x:[0,10],y:[100,0]};
  const broken={x:[0,null,10],y:[100,null,0]};
  assert.deepEqual(visibleYRange([joined],5,10),[0,55]);
  assert.deepEqual(visibleYRange([broken],5,10),[0,10]);
});

test("window controls and legend changes invoke the same scaling calculation",async()=>{
  const handlers={};
  const plot={data:[trace(),{x:[end],y:[200]}],layout:{meta:{generated_at:new Date(end).toISOString()}},on:(name,fn)=>{handlers[name]=fn;}};
  const updates=[];
  const plotly={
    relayout:async(_,update)=>{updates.push(update);},
    restyle:async(_,update,indices=plot.data.map((_,i)=>i))=>{
      indices.forEach((i,k)=>{plot.data[i].visible=Array.isArray(update.visible)?update.visible[k]:update.visible;});
      handlers.plotly_restyle();
    },
  };
  const controller=attachOverview(plot,plotly);
  await controller.setWindow(24);
  assert.deepEqual(updates.at(-1)["yaxis.range"],[0,250]);
  await controller.toggle(1);
  assert.deepEqual(updates.at(-1)["yaxis.range"],[0,65]);
  await controller.setWindow(168);
  assert.deepEqual(updates.at(-1)["yaxis.range"],[0,1000]);
  await controller.toggle(1,true);
  assert.deepEqual(updates.at(-1)["yaxis.range"],[0,250]);
  await controller.showAll();
  assert.deepEqual(updates.at(-1)["yaxis.range"],[0,1000]);
});
