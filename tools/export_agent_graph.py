"""Export the authoritative Agent graph as stable UTF-8 JSON."""
import argparse
import json
from pathlib import Path

from chain_eye.agents.graph import DEFAULT_AGENT_GRAPH


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    text=json.dumps(DEFAULT_AGENT_GRAPH.export(),ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text,encoding='utf-8')
        print(f'exported {args.output}')
    else:print(text,end='')


if __name__=='__main__':main()
