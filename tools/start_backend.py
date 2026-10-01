from pathlib import Path
import sys
import uvicorn
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend/src'))
if __name__=='__main__':uvicorn.run('chain_eye.api.app:create_app',factory=True,host='127.0.0.1',port=8000)
