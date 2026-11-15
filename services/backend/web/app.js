"use strict";
const $=id=>document.getElementById(id);
let token=localStorage.getItem('claimly.session')||'';
let thread=localStorage.getItem('claimly.thread')||'';
let busy=false, sourceUrl=null;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function notify(text){$('notice').textContent=text;}
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
async function api(path, options={}){
  const headers=new Headers(options.headers||{});
  if(token)headers.set('X-Demo-Session',token);
  if(options.body && !(options.body instanceof FormData))headers.set('Content-Type','application/json');
  const response=await fetch(path,{...options,headers});
  if(!response.ok){let detail;try{detail=await response.json();}catch{detail={};}
    const err=new Error(detail.error?.message||'The request could not be completed.');
    err.code=detail.error?.code;throw err;}
  if(response.status===204)return null;
  return response.json();
}
function mutation(body){return {method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)};}
async function bootstrap(){
  try{
    if(token)await api('/api/v1/entries?limit=1');
    else await newSession();
    await refresh();
  }catch(e){
    if(e.code==='DEMO_SESSION_EXPIRED'||e.code==='DEMO_SESSION_REQUIRED'){
      localStorage.removeItem('claimly.session');localStorage.removeItem('claimly.thread');token='';thread='';
      await newSession();await refresh();notify('A new private demo session has started.');
    }else notify(e.message);
  }
}
async function newSession(){
  const result=await api('/api/v1/demo/sessions',{method:'POST'});
  token=result.data.session_token;localStorage.setItem('claimly.session',token);
  localStorage.setItem('claimly.session_id',result.data.id);
}
async function collection(path){let items=[],cursor=null;do{const r=await api(path+(path.includes('?')?'&':'?')+'limit=100'+(cursor?'&cursor='+encodeURIComponent(cursor):''));items.push(...r.data);cursor=r.next_cursor;}while(cursor);return items;}
async function refresh(){
  const entries=await collection('/api/v1/entries');$('documents').replaceChildren();
  for(const entry of entries){for(const id of entry.document_ids){
    let doc;try{doc=(await api('/api/v1/documents/'+id)).data;}catch{continue;}
    const item=node('div',undefined,'document');item.append(node('strong',entry.title),node('span',doc.status==='ready'?'Ready for questions':doc.status));
    const actions=node('div',undefined,'actions');const preview=node('button','View source','secondary');preview.onclick=()=>openSource(id,1,'');
    const remove=node('button','Delete','secondary');remove.onclick=async()=>{try{await api('/api/v1/documents/'+id,{method:'DELETE'});await refresh();if(thread)await loadMessages();}catch(e){notify(e.message);}};
    actions.append(preview,remove);item.append(actions);$('documents').append(item);
  }}
  const threads=await collection('/api/v1/threads?scope=vault');$('conversations').replaceChildren(node('option','Start a conversation'));
  $('conversations').firstChild.value='';
  for(const t of threads){const o=node('option','Conversation · '+new Date(t.created_at).toLocaleString());o.value=t.id;$('conversations').append(o);}
  if(threads.some(t=>t.id===thread)){$('conversations').value=thread;await loadMessages();}
  else{thread='';localStorage.removeItem('claimly.thread');}
}
async function watch(id,onUpdate){
  for(let i=0;i<900;i++){
    const job=(await api('/api/v1/jobs/'+id)).data;if(onUpdate)onUpdate(job);
    if(job.status==='succeeded')return job;
    if(['failed','cancelled','stale'].includes(job.status))throw new Error(job.error?.message||'The task could not complete.');
    await pause(1200);
  }
  throw new Error('This task is still pending. Refresh later to check its status.');
}
$('upload-form').onsubmit=async event=>{
  event.preventDefault();const files=Array.from($('files').files);
  if(files.length>5){notify('Choose up to five documents in one batch.');return;}
  $('upload-button').disabled=true;notify('');
  try{for(const file of files){
    if(file.size>10*1024*1024)throw new Error('Each document must be 10 MB or smaller.');
    const item=node('div',undefined,'upload-status');item.append(node('strong',file.name));const status=node('p','Uploading…');item.append(status);$('uploads').prepend(item);
    const entry=(await api('/api/v1/entries',mutation({title:'Pending document',category:'other'}))).data;
    const form=new FormData();form.append('entry_id',entry.id);form.append('file',file);
    const result=(await api('/api/v1/documents',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:form})).data;
    const preview=node('button','View original','secondary');preview.onclick=()=>openSource(result.document.id,1,'');item.append(preview);
    try{
      const job=await watch(result.job.id,j=>{status.textContent=j.status==='running'?'Reading your document…':'Waiting to process…';});
      status.textContent=job.result.review_required?'Source review required before this document can be searched.':'Ready for questions';
      if(job.result.review_required){const retry=node('button','Check review status','secondary');retry.onclick=async()=>{try{const d=(await api('/api/v1/documents/'+result.document.id)).data;status.textContent=d.status==='ready'?'Ready for questions':d.status==='processing'?'Preparing your document for search…':'Source review is still required.';await refresh();}catch(e){notify(e.message);}};item.append(retry);}
    }catch(e){status.textContent=e.message;preview.remove();}
    await refresh();
  }}catch(e){notify(e.message);}finally{$('upload-button').disabled=false;$('files').value='';}
};
function showMessage(message){
  const item=node('article',undefined,'message '+message.role);item.append(node('div',message.role==='assistant'?'Claimly':'You','role'),node('div',message.content,'text'));
  if(message.questions.length){const qs=node('ul');for(const q of message.questions)qs.append(node('li',q));item.append(qs);}
  if(message.evidence_refs.length){const refs=node('div',undefined,'citations');for(const ref of message.evidence_refs){const b=node('button','Source · page '+ref.page,'citation');b.onclick=()=>openSource(ref.document_id,ref.page,ref.quote);refs.append(b);}item.append(refs);}
  $('messages').append(item);$('messages').scrollTop=$('messages').scrollHeight;
}
async function loadMessages(){
  const messages=await collection('/api/v1/threads/'+thread+'/messages');$('messages').replaceChildren();
  for(const message of messages)showMessage(message);
}
$('chat-form').onsubmit=async event=>{
  event.preventDefault();if(busy)return;busy=true;$('send-button').disabled=true;notify('');
  try{
    if(!thread){thread=(await api('/api/v1/threads',mutation({scope:'vault',entry_id:null,case_id:null,document_ids:[]}))).data.id;localStorage.setItem('claimly.thread',thread);}
    const result=(await api('/api/v1/threads/'+thread+'/messages',mutation({content:$('question').value,purpose:'answer'}))).data;
    $('question').value='';await loadMessages();$('send-button').textContent='Finding evidence…';
    await watch(result.job.id);await refresh();await loadMessages();
  }catch(e){notify(e.message);}finally{busy=false;$('send-button').disabled=false;$('send-button').textContent='Send question';}
};
$('new-chat').onclick=()=>{thread='';localStorage.removeItem('claimly.thread');$('conversations').value='';$('messages').replaceChildren(node('p','Ask a question about your reviewed documents.','empty'));};
$('conversations').onchange=async()=>{thread=$('conversations').value;localStorage.setItem('claimly.thread',thread);if(thread)await loadMessages();else $('new-chat').click();};
async function openSource(id,page,quote){
  try{const r=await fetch('/api/v1/documents/'+id+'/content',{headers:{'X-Demo-Session':token}});if(!r.ok)throw new Error('This source is no longer available in this session.');
    if(sourceUrl)URL.revokeObjectURL(sourceUrl);sourceUrl=URL.createObjectURL(await r.blob());
    $('source-title').textContent='Original source · page '+page;$('source-quote').textContent=quote;$('source-quote').hidden=!quote;
    $('source-frame').src=sourceUrl+'#page='+page;$('source').hidden=false;$('source').scrollIntoView({behavior:'smooth'});
  }catch(e){notify(e.message);}
}
$('close-source').onclick=()=>{$('source').hidden=true;$('source-frame').removeAttribute('src');if(sourceUrl)URL.revokeObjectURL(sourceUrl);sourceUrl=null;};
bootstrap();
