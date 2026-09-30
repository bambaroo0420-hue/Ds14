import argparse,os,sys
from check_environment import check
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--project',help='Existing v1 project folder or new project folder');a=p.parse_args()
    if not check():sys.exit(1)
    try:import uvicorn
    except (ImportError,OSError) as exc:
        print(f'Web server import failed: {exc}\nRun diagnose_windows.bat. No packages are installed automatically.',file=sys.stderr)
        sys.exit(1)
    if a.project:os.environ['TEM_PROJECT_DIR']=a.project
    uvicorn.run('tem_analyzer.api:app',host='127.0.0.1',port=a.port)
