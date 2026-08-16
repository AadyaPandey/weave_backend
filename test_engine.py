import asyncio
from app.db import init_db
from app.engine.engine import execute
w={'id':999,'name':'test','nodes':[{'id':'i','type':'text','config':{'text':'{{input.message}}'}},{'id':'c','type':'condition','config':{'left':'{{nodes.i.output.text}}','operator':'contains','right':'urgent'}},{'id':'yes','type':'response','config':{'value':'URGENT'}},{'id':'no','type':'response','config':{'value':'NORMAL'}}],'edges':[{'id':'1','source':'i','target':'c'},{'id':'2','source':'c','target':'yes','source_handle':'true'},{'id':'3','source':'c','target':'no','source_handle':'false'}]}
async def main():
 init_db();_,out=await execute(w,{'message':'urgent issue'});assert out=='URGENT';print('branch test passed:',out)
asyncio.run(main())
