(() => {
  const floors=['Terreo','Piso 1','Piso 2'];
  const floorSelect=document.getElementById('mallFloorSelect'),stage=document.getElementById('mallStage'),layer=document.getElementById('mallLayer'),markerLayer=document.getElementById('mallMarkers');
  const items=[...document.querySelectorAll('.mall-result')],search=document.getElementById('mallSearch'),clear=document.getElementById('mallClear'),count=document.getElementById('mallResultCount'),empty=document.getElementById('mallEmpty');
  const popup=document.getElementById('mallPopup'),popupName=document.getElementById('mallPopupName'),popupCategory=document.getElementById('mallPopupCategory'),popupDescription=document.getElementById('mallPopupDescription'),popupMeta=document.getElementById('mallPopupMeta'),popupLogo=document.getElementById('mallPopupLogo'),popupDetail=document.getElementById('mallPopupDetail');
  const routePath=document.getElementById('mallRoutePath'),routeHint=document.getElementById('mallRouteHint');
  const floorLabel=floor=>floor==='Terreo'?'Térreo':floor;
  const normalize=value=>(value||'').toString().toLocaleLowerCase('pt-BR').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim();
  const canonicalFloor=value=>{const key=normalize(value).replace(/\s+/g,' ').trim();if(['terreo','piso terreo','piso 0','0'].includes(key))return 'Terreo';if(['piso 1','1'].includes(key))return 'Piso 1';if(['piso 2','2'].includes(key))return 'Piso 2';return value||'Terreo';};
  items.forEach(item=>{item.dataset.floor=canonicalFloor(item.dataset.floor);});
  let state={floor:'Terreo',category:'all',query:'',scale:1,x:0,y:0,selected:null,selectedMarker:null,dragging:false,startX:0,startY:0};
  const markers=new Map();

  function isFood(item){return item.dataset.kind==='store'&&item.dataset.food==='true';}
  function results(){
    const q=normalize(state.query);
    return items.filter(item=>{
      const categoryOk=state.category==='all'||(state.category==='stores'&&item.dataset.kind==='store')||(state.category==='food'&&isFood(item))||(state.category.startsWith('cat:')&&item.dataset.kind==='store'&&normalize(item.dataset.category)===state.category.slice(4));
      const hay=normalize([item.dataset.name,item.dataset.category,item.dataset.code,item.dataset.description].join(' '));
      return item.dataset.floor===state.floor&&categoryOk&&(!q||hay.includes(q));
    });
  }
  function coordinates(item,index){
    const x=Number(item.dataset.x),y=Number(item.dataset.y),valid=item.dataset.x!==''&&item.dataset.y!==''&&Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=100&&y>=0&&y<=100;
    if(valid)return{x,y,approx:false};
    if(item.dataset.kind==='poi'){
      const poi=[{x:12.3,y:50},{x:87.5,y:50},{x:50,y:80.8}];
      return{...poi[index%poi.length],approx:true};
    }
    // Prévia visual determinística: não grava nem altera coordenadas do cadastro.
    const preview=[{x:20,y:25},{x:32,y:25},{x:44,y:25},{x:56,y:25},{x:68,y:25},{x:80,y:25},{x:20,y:75},{x:32,y:75},{x:44,y:75},{x:56,y:75},{x:68,y:75},{x:80,y:75},{x:16,y:37},{x:16,y:63},{x:84,y:37},{x:84,y:63},{x:35,y:18},{x:50,y:18},{x:65,y:18},{x:35,y:82},{x:50,y:82},{x:65,y:82}];
    return{...preview[index%preview.length],approx:true};
  }
  function makeMarkers(){
    const stores=items.filter(item=>item.dataset.kind==='store');
    floors.forEach(floor=>{
      stores.filter(item=>item.dataset.floor===floor).forEach((item,index)=>{
        const point=coordinates(item,index),button=document.createElement('button');
        button.type='button';button.className='mall-marker';button.dataset.id=item.dataset.id;button.dataset.floor=floor;
        button.style.left=point.x+'%';button.style.top=point.y+'%';button.title=item.dataset.name;
        if(isFood(item))button.classList.add('food');
        else if(/servic|saude|beleza|farmac/.test(normalize(item.dataset.category)))button.classList.add('service');
        else if(/moda|roupa|vestu|calcado|acessor/.test(normalize(item.dataset.category)))button.classList.add('apparel');
        else if(/eletron|tecnolog|celular|informat/.test(normalize(item.dataset.category)))button.classList.add('digital');
        else if(/entreten|cinema|jogos|lazer/.test(normalize(item.dataset.category)))button.classList.add('leisure');
        else button.classList.add('other');
        if(item.dataset.logo){const img=document.createElement('img');img.className='mall-marker-logo';img.src=item.dataset.logo;img.alt='';img.loading='lazy';img.onerror=()=>img.remove();button.appendChild(img);}
        const initials=document.createElement('span');initials.className='mall-marker-fallback';initials.textContent=(item.dataset.name||'').trim().slice(0,2).toUpperCase();button.appendChild(initials);
        const label=document.createElement('span');label.className='mall-marker-label';label.textContent=item.dataset.name;button.appendChild(label);
        button.setAttribute('aria-label','Abrir '+item.dataset.name);button.addEventListener('click',()=>select(item));markerLayer.appendChild(button);markers.set(item.dataset.id,button);
      });
      items.filter(item=>item.dataset.kind==='poi'&&item.dataset.floor===floor).forEach((item,index)=>{
        const point=coordinates(item,index),button=document.createElement('button');button.type='button';button.className='mall-marker poi';button.dataset.id=item.dataset.id;button.dataset.floor=floor;button.style.left=point.x+'%';button.style.top=point.y+'%';button.textContent=item.dataset.icon||(/banheiro|sanitario|toalete/.test(normalize(item.dataset.name))?'WC':'•');button.title=item.dataset.name;button.setAttribute('aria-label','Abrir '+item.dataset.name);button.addEventListener('click',()=>select(item));markerLayer.appendChild(button);markers.set(item.dataset.id,button);
      });
    });
  }
  function render(){
    const visible=results(),ids=new Set(visible.map(item=>item.dataset.id));
    items.forEach(item=>{item.hidden=!ids.has(item.dataset.id);item.classList.toggle('active',item.dataset.id===state.selected);});
    markers.forEach((marker,id)=>{marker.hidden=!ids.has(id);marker.classList.toggle('selected',id===state.selected);});
    count.textContent=String(visible.length);empty.hidden=visible.length>0;
    const label=visible.length===1?'local': 'locais';document.getElementById('mallFloorCount').textContent=visible.length+' '+label;
    document.getElementById('mallCurrentFloor').textContent=floorLabel(state.floor);document.getElementById('mallFloorIndicator').firstChild.textContent=floorLabel(state.floor)+' · ';
    document.querySelector('.mall-you-are-here').hidden=state.floor!=='Terreo';
    document.querySelectorAll('[data-floor-tab]').forEach(tab=>{const active=tab.dataset.floorTab===state.floor;tab.classList.toggle('active',active);tab.setAttribute('aria-pressed',active?'true':'false');});
    document.getElementById('mallFoodArea').style.display=state.floor==='Piso 2'?'':'none';document.querySelector('.mall-common-area').style.display=state.floor==='Piso 2'?'none':'';
    if(state.selected&&!ids.has(state.selected))closePopup();
    scheduleDensity();
  }
  function applyTransform(){layer.style.transform=`translate(calc(-50% + ${state.x}px),calc(-50% + ${state.y}px)) scale(${state.scale})`;scheduleDensity();if(state.selectedMarker&&!popup.hidden)requestAnimationFrame(positionPopup);}
  function centerMarker(marker){if(!marker)return;const rect=stage.getBoundingClientRect(),point=marker.getBoundingClientRect();state.scale=Math.max(state.scale,1.25);state.x+=(rect.left+rect.width/2)-(point.left+point.width/2);state.y+=(rect.top+rect.height/2)-(point.top+point.height/2);applyTransform();setTimeout(()=>requestAnimationFrame(positionPopup),260);}
  function positionPopup(){if(popup.hidden)return;const stageRect=stage.getBoundingClientRect(),target=state.selectedMarker?.getBoundingClientRect();const w=popup.offsetWidth,h=popup.offsetHeight;let x=target?target.left-stageRect.left+22:stageRect.width/2-w/2,y=target?target.top-stageRect.top-h/2:stageRect.height/2-h/2;if(x+w>stageRect.width-12)x=(target?target.left-stageRect.left-w-18:stageRect.width-w-12);x=Math.max(12,Math.min(stageRect.width-w-12,x));y=Math.max(12,Math.min(stageRect.height-h-12,y));popup.style.left=x+'px';popup.style.top=y+'px';}
  function openPopup(item){
    state.selected=item.dataset.id;state.selectedMarker=markers.get(state.selected)||null;
    popupName.textContent=item.dataset.name;popupCategory.textContent=item.dataset.category||'Estabelecimento';
    popupDescription.textContent=item.dataset.description||'';popupDescription.hidden=!item.dataset.description;
    popupMeta.replaceChildren();[["Piso",floorLabel(item.dataset.floor)],["Unidade",item.dataset.code],["Horário",item.dataset.hours],["Telefone",item.dataset.phone]].forEach(([label,value])=>{if(value){const span=document.createElement('span');span.textContent=label+': '+value;popupMeta.appendChild(span);}});
    popupLogo.hidden=!item.dataset.logo;if(item.dataset.logo){popupLogo.src=item.dataset.logo;popupLogo.alt='Logo de '+item.dataset.name;}
    popupDetail.hidden=!item.dataset.detailUrl;if(item.dataset.detailUrl)popupDetail.href=item.dataset.detailUrl;
    popup.hidden=false;if(state.selectedMarker)centerMarker(state.selectedMarker);requestAnimationFrame(()=>requestAnimationFrame(positionPopup));render();
  }
  function select(item){if(item.dataset.floor!==state.floor){state.floor=item.dataset.floor;floorSelect.value=state.floor;state.scale=1;state.x=0;state.y=0;applyTransform();}openPopup(item);}
  function closePopup(){popup.hidden=true;state.selected=null;state.selectedMarker=null;routePath.setAttribute('d','');routeHint.hidden=true;render();}
  function showRoute(item){const marker=markers.get(item.dataset.id);if(!marker)return;const endX=parseFloat(marker.style.left),endY=parseFloat(marker.style.top),crossFloor=item.dataset.floor!=='Terreo';let startX=13,startY=88;if(crossFloor){const connectorItems=items.filter(entry=>entry.dataset.kind==='poi'&&entry.dataset.floor===item.dataset.floor&&/elevador|escada/.test(normalize(entry.dataset.name)));const connectors=connectorItems.map(entry=>markers.get(entry.dataset.id)).filter(Boolean).map(entry=>({x:parseFloat(entry.style.left),y:parseFloat(entry.style.top)}));const choices=connectors.length?connectors:[{x:12.3,y:50},{x:87.5,y:50},{x:50,y:80.8}];choices.sort((a,b)=>Math.hypot(a.x-endX,a.y-endY)-Math.hypot(b.x-endX,b.y-endY));startX=choices[0].x;startY=choices[0].y;}const dx=endX-startX,dy=endY-startY,distance=Math.hypot(dx,dy),minutes=Math.max(1,Math.round(distance/9));routePath.setAttribute('d',`M ${startX} ${startY} C ${startX+dx*.25} ${startY+dy*.1}, ${startX+dx*.72} ${endY-dy*.18}, ${endX} ${endY}`);routeHint.textContent=crossFloor?`Primeiro, vá ao elevador ou à escada rolante no Térreo. O mapa mostra o trecho no ${floorLabel(item.dataset.floor)}: cerca de ${minutes} min a pé até ${item.dataset.name}.`:`Siga o caminho destacado até ${item.dataset.name} · cerca de ${minutes} min a pé.`;routeHint.hidden=false;centerMarker(marker);}
  function scheduleDensity(){requestAnimationFrame(()=>{const visible=[...markers.values()].filter(m=>!m.hidden&&!m.classList.contains('poi'));visible.forEach(m=>m.classList.remove('dense'));if(state.scale>1.5)return;const boxes=visible.map(marker=>({marker,rect:marker.getBoundingClientRect()}));for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){const a=boxes[i],b=boxes[j];if(Math.abs(a.rect.left-b.rect.left)<Math.max(a.rect.width,b.rect.width)*.72&&Math.abs(a.rect.top-b.rect.top)<Math.max(a.rect.height,b.rect.height)*.72){a.marker.classList.add('dense');b.marker.classList.add('dense');}}});}
  function setCategory(value){state.category=value;document.querySelectorAll('[data-category-filter]').forEach(button=>{const active=button.dataset.categoryFilter===value;button.classList.toggle('active',active);button.setAttribute('aria-pressed',active?'true':'false');});render();}
  const categoryExtra=document.getElementById('mallCategoryExtra');[...new Set(items.filter(item=>item.dataset.kind==='store').map(item=>item.dataset.category).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt-BR')).forEach(category=>{const button=document.createElement('button');button.type='button';button.className='mall-category';button.dataset.categoryFilter='cat:'+normalize(category);button.textContent=category;button.setAttribute('aria-pressed','false');categoryExtra.appendChild(button);});

  floorSelect.addEventListener('change',()=>{state.floor=floors.includes(floorSelect.value)?floorSelect.value:'Terreo';state.scale=1;state.x=0;state.y=0;applyTransform();render();});
  document.querySelectorAll('[data-category-filter]').forEach(button=>button.addEventListener('click',()=>setCategory(button.dataset.categoryFilter)));
  document.querySelectorAll('[data-floor-tab]').forEach(button=>button.addEventListener('click',()=>{floorSelect.value=button.dataset.floorTab;floorSelect.dispatchEvent(new Event('change',{bubbles:true}));}));
  search.addEventListener('input',()=>{state.query=search.value;clear.hidden=!state.query;render();});clear.addEventListener('click',()=>{search.value='';state.query='';clear.hidden=true;search.focus();render();});
  items.forEach(item=>item.addEventListener('click',()=>select(item)));
  document.getElementById('mallZoomIn').addEventListener('click',()=>{state.scale=Math.min(2.8,state.scale+.2);applyTransform();});
  document.getElementById('mallZoomOut').addEventListener('click',()=>{state.scale=Math.max(.8,state.scale-.2);applyTransform();});
  document.getElementById('mallReset').addEventListener('click',()=>{state.scale=1;state.x=0;state.y=0;applyTransform();});
  document.getElementById('mallPopupRoute').addEventListener('click',()=>{const item=items.find(entry=>entry.dataset.id===state.selected);if(item)showRoute(item);});
  document.getElementById('mallPopupClose').addEventListener('click',closePopup);document.getElementById('mallPopupCenter').addEventListener('click',()=>centerMarker(state.selectedMarker));
  stage.addEventListener('click',event=>{if(!popup.hidden&&!event.target.closest('.mall-popup,.mall-marker'))closePopup();});
  const pointers=new Map();let pinchStart=null;
  stage.addEventListener('pointerdown',event=>{if(event.target.closest('button,a,.mall-popup'))return;pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});stage.setPointerCapture(event.pointerId);if(pointers.size===2){const pair=[...pointers.values()];pinchStart={distance:Math.hypot(pair[0].x-pair[1].x,pair[0].y-pair[1].y),scale:state.scale};state.dragging=false;}else{state.dragging=true;state.startX=event.clientX-state.x;state.startY=event.clientY-state.y;stage.classList.add('dragging');}});
  stage.addEventListener('pointermove',event=>{if(!pointers.has(event.pointerId))return;pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});if(pointers.size>1&&pinchStart){const pair=[...pointers.values()],distance=Math.hypot(pair[0].x-pair[1].x,pair[0].y-pair[1].y);state.scale=Math.min(2.8,Math.max(1,pinchStart.scale*distance/pinchStart.distance));applyTransform();return;}if(state.dragging){state.x=event.clientX-state.startX;state.y=event.clientY-state.startY;applyTransform();}});
  ['pointerup','pointercancel','lostpointercapture'].forEach(name=>stage.addEventListener(name,event=>{pointers.delete(event.pointerId);if(pointers.size<2)pinchStart=null;if(!pointers.size){state.dragging=false;stage.classList.remove('dragging');}}));
  stage.addEventListener('wheel',event=>{event.preventDefault();state.scale=Math.min(2.8,Math.max(.8,state.scale+(event.deltaY<0?.12:-.12)));applyTransform();},{passive:false});
  window.addEventListener('resize',()=>{scheduleDensity();if(!popup.hidden)positionPopup();});document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!popup.hidden)closePopup();});
  let idleTimer;function resetIdle(){clearTimeout(idleTimer);idleTimer=setTimeout(()=>{search.value='';state.query='';clear.hidden=true;state.category='all';state.floor='Terreo';floorSelect.value='Terreo';state.scale=1;state.x=0;state.y=0;closePopup();setCategory('all');applyTransform();render();},60000);}
  document.addEventListener('pointerdown',resetIdle,{passive:true});document.addEventListener('keydown',event=>{if(event.ctrlKey&&['+','=','-','0'].includes(event.key)){event.preventDefault();}resetIdle();});search.addEventListener('input',resetIdle);stage.addEventListener('contextmenu',event=>event.preventDefault());document.addEventListener('contextmenu',event=>{if(event.target.closest('.mall-map-page'))event.preventDefault();});
  makeMarkers();render();resetIdle();
})();
