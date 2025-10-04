const form=document.getElementById('plagiarismForm');
const progress=document.getElementById('progress');
const resultsDiv=document.getElementById('results');
const reportDiv=document.getElementById('report');

form.addEventListener('submit', async (e)=>{
  e.preventDefault();
  resultsDiv.innerHTML='';
  reportDiv.innerHTML='';
  progress.style.display='block';

  const formData=new FormData();
  const text=document.getElementById('text').value;
  const file=document.getElementById('file').files[0];
  if(text) formData.append('text',text);
  if(file) formData.append('file',file);

  try{
    const res=await fetch('http://localhost:5000/api/check',{method:'POST',body:formData});
    const data=await res.json();
    progress.style.display='none';
    if(data.error){ resultsDiv.innerHTML=data.error; return; }
    data.matches.forEach((m,i)=>{
      const div=document.createElement('div');
      div.innerHTML=`<h3>Match #${i+1}</h3><p>Source: ${m.source}</p><p>Similarity: ${m.similarity}%</p><p>Text: ${m.text.substring(0,200)}...</p>`;
      resultsDiv.appendChild(div);
    });
    if(data.pdf){
      const a=document.createElement('a');
      a.href=data.pdf; a.target='_blank'; a.textContent='Download PDF Report';
      reportDiv.appendChild(a);
    }
  }catch(err){ progress.style.display='none'; resultsDiv.innerHTML='Error: '+err; }
});
