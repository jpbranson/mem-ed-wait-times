// Origin selection is independent of routing, age, and destination eligibility.
export function validOrigin(point) {
  return !!point && typeof point.latitude==="number" && Number.isFinite(point.latitude) && Math.abs(point.latitude)<=90 &&
    typeof point.longitude==="number" && Number.isFinite(point.longitude) && Math.abs(point.longitude)<=180;
}

export function readOrigin(latitude,longitude) {
  if(!String(latitude).trim() || !String(longitude).trim()) return null;
  const point={latitude:Number(latitude),longitude:Number(longitude)};
  return validOrigin(point) ? point : null;
}

export function locate(geolocation,{secure=globalThis.isSecureContext!==false,timeoutMs=12000}={}) {
  return new Promise((resolve,reject)=>{
    if(!secure) return reject(Error("Location needs HTTPS or localhost · choose the map or enter coordinates"));
    if(!geolocation) return reject(Error("Location access unavailable · choose the map or enter coordinates"));
    const timer=setTimeout(()=>reject(Error("Location timed out · choose the map or try again")),timeoutMs);
    const fail=message=>{clearTimeout(timer);reject(Error(message));};
    try {
      geolocation.getCurrentPosition(p=>{
        const point={latitude:p?.coords?.latitude,longitude:p?.coords?.longitude};
        if(!validOrigin(point)) return fail("Location unavailable · choose the map or enter coordinates");
        clearTimeout(timer);resolve(point);
      },e=>fail(e?.code===1 ? "Location permission denied · allow location in your browser, or choose the map" :
        e?.code===3 ? "Location timed out · choose the map or try again" : "Location unavailable · choose the map or enter coordinates"),
      {enableHighAccuracy:false,maximumAge:0,timeout:10000});
    } catch { fail("Location unavailable · choose the map or enter coordinates"); }
  });
}

const loadMap=options=>import("./origin-map.mjs").then(module=>module.createOriginMap(options));

export function mountOriginPicker(root,{onChange=()=>{},geolocation=globalThis.navigator?.geolocation,
  secure=globalThis.isSecureContext!==false,createMap=loadMap,eventTarget=globalThis,
  Observer=globalThis.IntersectionObserver}={}) {
  const lat=root.querySelector("[name=latitude]"),lon=root.querySelector("[name=longitude]");
  const button=root.querySelector(".travel-location"),status=root.querySelector(".origin-status");
  const container=root.querySelector(".origin-map"),mapStatus=root.querySelector(".origin-map-status");
  const center=root.querySelector(".origin-center"),retry=root.querySelector(".origin-map-retry");
  let serial=0,locating=false,map=null,mapPending=false;
  const value=()=>readOrigin(lat.value,lon.value);
  function render() {
    button.disabled=locating;
    button.textContent=locating ? "Finding your location…" : "Use my location";
    button.setAttribute("aria-busy",String(locating));
    center.disabled=!map;
  }
  function invalidate() { serial++;locating=false;onChange();render(); }
  function select(point,{recenter=false,message="Origin selected · move the pin to adjust"}={}) {
    if(!validOrigin(point)) return;
    lat.value=point.latitude.toFixed(6);lon.value=point.longitude.toFixed(6);
    invalidate();map?.setOrigin(value(),{recenter});status.textContent=message;
  }
  async function startMap() {
    if(mapPending || map) return;
    mapPending=true;retry.hidden=true;mapStatus.textContent="Loading map…";
    try {
      map=await createMap({container,onSelect:point=>select(point),onStatus:message=>{mapStatus.textContent=message;}});
      if(value()) map.setOrigin(value(),{recenter:true});
    } catch { mapStatus.textContent="Map unavailable · use your location or enter coordinates";retry.hidden=false; }
    finally { mapPending=false;render(); }
  }
  if(Observer) {
    const observer=new Observer(entries=>{
      if(entries.some(entry=>entry.isIntersecting)) {observer.disconnect();startMap();}
    },{rootMargin:"200px"});
    observer.observe(container);
  } else startMap();
  retry.addEventListener("click",startMap);
  center.addEventListener("click",()=>{if(map) select(map.getCenter());});
  for(const input of [lat,lon]) {
    input.addEventListener("input",()=>{
      invalidate();map?.setOrigin(value());
      status.textContent=value() ? "Origin selected" : "Choose a point on the map or enter both coordinates";
    });
    input.addEventListener("change",()=>{if(value()) map?.setOrigin(value(),{recenter:true});});
  }
  button.addEventListener("click",async()=>{
    invalidate();const token=serial;locating=true;status.textContent="Waiting for your browser’s location…";onChange();render();
    try {
      const point=await locate(geolocation,{secure});
      if(token===serial) select(point,{recenter:true,message:"Location selected · check the pin and adjust if needed"});
    } catch(e) { if(token===serial) {locating=false;status.textContent=e.message;onChange();render();} }
  });
  function clear() {
    lat.value=lon.value="";invalidate();map?.clear();status.textContent="Origin cleared";
  }
  root.querySelector(".travel-clear").addEventListener("click",clear);
  eventTarget.addEventListener("pagehide",clear);
  render();
  return {value,clear,isLocating:()=>locating};
}
