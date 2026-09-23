import {Map,Marker,NavigationControl} from "./vendor/maplibre/maplibre-gl.mjs";
import {validOrigin} from "./origin.mjs";

const initial={center:[-89.97,35.14],zoom:9.5};
const point=lngLat=>({latitude:lngLat.lat,longitude:lngLat.wrap().lng});

export async function createOriginMap({container,onSelect,onStatus}) {
  // Style and Inter are local. Only visible-area map data/sprites use OpenFreeMap.
  const response=await fetch(new URL("./origin-map-style.json",import.meta.url),{signal:AbortSignal.timeout(10000)});
  if(!response.ok) throw Error("Map style unavailable");
  const style=await response.json();
  await document.fonts.load("16px Inter");
  const map=new Map({container,style,...initial,minZoom:2,maxZoom:18,maxPitch:0,
    hash:false,renderWorldCopies:false,attributionControl:false,
    dragRotate:false,pitchWithRotate:false,touchPitch:false,scrollZoom:false,
    cooperativeGestures:true,collectResourceTiming:false});
  map.touchZoomRotate.disableRotation();
  map.addControl(new NavigationControl({showCompass:false}),"top-right");
  map.getCanvas().setAttribute("aria-label","Origin map. Arrow keys pan; plus and minus zoom. Use map center to select.");
  map.getCanvas().setAttribute("aria-describedby","origin-map-help");
  let marker=null,hasError=false;
  map.on("load",()=>{if(!hasError) onStatus("");});
  map.on("error",()=>{hasError=true;onStatus("Some map details are unavailable · use coordinates if needed");});
  map.on("click",event=>{const selected=point(event.lngLat);if(validOrigin(selected)) onSelect(selected);});
  // Only our marker is shown. Basemap POIs are not verified routing destinations.
  function setOrigin(selected,{recenter=false}={}) {
    if(!selected) {marker?.remove();marker=null;return;}
    if(!marker) {
      marker=new Marker({color:"#70d9cf",draggable:true}).setLngLat([selected.longitude,selected.latitude]).addTo(map);
      marker.getElement().setAttribute("aria-label","Selected origin; drag to adjust");
      marker.getElement().setAttribute("role","img");
      marker.getElement().setAttribute("tabindex","-1");
      const active=marker;
      marker.on("dragend",()=>{if(marker===active) onSelect(point(active.getLngLat()));});
    } else marker.setLngLat([selected.longitude,selected.latitude]);
    if(recenter) map.jumpTo({center:[selected.longitude,selected.latitude],zoom:Math.max(map.getZoom(),12)});
  }
  // Fit changes caused by responsive layout, not only window resizes.
  const resize=new ResizeObserver(()=>map.resize());resize.observe(container);
  return {setOrigin,getCenter:()=>point(map.getCenter()),clear(){setOrigin(null);map.jumpTo(initial);}};
}
