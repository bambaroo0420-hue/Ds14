import argparse,os
import uvicorn
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--project',help='Existing v1 project folder or new project folder');a=p.parse_args()
    if a.project:os.environ['TEM_PROJECT_DIR']=a.project
    uvicorn.run('tem_analyzer.api:app',host='127.0.0.1',port=a.port)
