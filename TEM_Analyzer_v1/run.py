import argparse
import uvicorn
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);a=p.parse_args()
    uvicorn.run('tem_analyzer.api:app',host='127.0.0.1',port=a.port)
