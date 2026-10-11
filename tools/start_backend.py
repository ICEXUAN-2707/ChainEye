from pathlib import Path
import os
import sys

from dotenv import load_dotenv
import uvicorn

root=Path(__file__).resolve().parents[1]
if os.getenv('PYTHON_DOTENV_DISABLED','').casefold() not in {'1','true','yes'}:
    load_dotenv(dotenv_path=root/'.env',override=False)
sys.path.insert(0,str(root/'backend/src'))
if __name__=='__main__':uvicorn.run('chain_eye.api.app:create_app',factory=True,host='127.0.0.1',port=8000)
