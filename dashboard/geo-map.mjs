import {Map as MapLibre, Marker, NavigationControl} from "./vendor/maplibre/maplibre-gl.mjs";

export async function createGeoMap({container, points, onSelect, onStatus}) {
  // Same local style and Inter labels as the origin map; only the viewed area's
  // tiles and sprites come from OpenFreeMap. No user location is involved.
  const response=await fetch(new URL("./origin-map-style.json",import.meta.url),{signal:AbortSignal.timeout(10000)});
  if(!response.ok) throw Error("Map style unavailable");
  const style=await response.json();
  await document.fonts.load("16px Inter");
  const bounds=chosen=>{
    const lons=chosen.map(p=>p.campus.longitude), lats=chosen.map(p=>p.campus.latitude);
    return [[Math.min(...lons),Math.min(...lats)],[Math.max(...lons),Math.max(...lats)]];
  };
  const framing={padding:48,maxZoom:11};
  const map=new MapLibre({container,style,bounds:bounds(points),
    fitBoundsOptions:framing,minZoom:4,maxZoom:14,maxPitch:0,hash:false,renderWorldCopies:false,
    attributionControl:false,dragRotate:false,pitchWithRotate:false,touchPitch:false,scrollZoom:false,
    cooperativeGestures:true,collectResourceTiming:false});
  map.touchZoomRotate.disableRotation();
  map.addControl(new NavigationControl({showCompass:false}),"top-right");
  map.getCanvas().setAttribute("aria-label","Hospital map. Arrow keys pan; plus and minus zoom. Hospital markers follow.");
  map.on("error",()=>onStatus("Some map details are unavailable"));
  // MapLibre owns each wrapper's classes and position; only the inner button is restyled.
  const buttons=new Map();
  for(const point of points) {
    const wrapper=document.createElement("div"), button=document.createElement("button");
    button.type="button";
    button.className="geo-marker geo-empty";
    button.addEventListener("click",()=>onSelect(point.slug));
    wrapper.append(button);
    buttons.set(point.slug,button);
    new Marker({element:wrapper}).setLngLat([point.campus.longitude,point.campus.latitude]).addTo(map);
  }
  // Keep the chosen hospitals framed as the layout changes, until the user pans or zooms.
  let framed=points, moved=false;
  map.on("movestart",event=>{ if(event.originalEvent) moved=true; });
  const resize=new ResizeObserver(()=>{ map.resize(); if(!moved) map.fitBounds(bounds(framed),{...framing,animate:false}); });
  resize.observe(container);
  return {
    fit(slugs) {
      const chosen=points.filter(p=>slugs.includes(p.slug));
      if(!chosen.length) return;
      framed=chosen; moved=false;
      map.fitBounds(bounds(chosen),{...framing,animate:!matchMedia("(prefers-reduced-motion: reduce)").matches});
    },
    update(entries, focus) {
      for(const entry of entries) {
        const button=buttons.get(entry.slug);
        if(!button) continue;
        const selected=entry.slug===focus;
        button.className=`geo-marker geo-${entry.kind} heat-${entry.band}${selected ? " selected" : ""}`;
        button.textContent=entry.glyph;
        button.title=entry.label;
        button.setAttribute("aria-label",`${entry.label}. Show in focus chart`);
        button.setAttribute("aria-pressed",String(selected));
      }
    }
  };
}
