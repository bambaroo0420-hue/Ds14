"""Local isolated audit runner. Keeps test projects as evidence (no source edits)."""
from pathlib import Path
import argparse, json, os, sys, tempfile, time, unittest, uuid

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-output/gap-bridge-20261001'


def main():
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument('--all',action='store_true');parser.add_argument('--output');args=parser.parse_args()
    if args.output:OUT=ROOT/'test-output'/args.output
    OUT.mkdir(parents=True,exist_ok=True)
    # Python 3.13 mode-0700 tempfile ACLs fail in this managed Windows sandbox.
    # Ordinary task-owned folders keep the same tests isolated without changing OS ACLs.
    class LocalTemp:
        def __init__(self,*a,**kw):
            self.name=str(OUT/('case-'+uuid.uuid4().hex));Path(self.name).mkdir()
        def __enter__(self):return self.name
        def __exit__(self,*a):self.cleanup()
        def cleanup(self):pass
    tempfile.TemporaryDirectory=LocalTemp
    sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py' if args.all else 'test_gap_bridge.py')
    start=time.perf_counter()
    with (OUT/('all-tests.log' if args.all else 'focused-tests.log')).open('w',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'seconds':time.perf_counter()-start,'temp_acl_workaround':True}
    (OUT/('all-tests.json' if args.all else 'focused-tests.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));print('\n'.join(text for _,text in result.failures+result.errors))
    return not result.wasSuccessful()


if __name__=='__main__':raise SystemExit(main())
