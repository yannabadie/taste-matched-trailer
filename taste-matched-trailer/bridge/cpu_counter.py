"""Dynamic CPU-only tokenizer worker; no model or network execution."""
from pathlib import Path
import hashlib
import json
import os
import sys

MODEL = (Path.home() / 'Movies/StudioVideoLocal/models/qwen38-27b-orcarouter-mlx/8-bit')

def main():
    def audit(event, args):
        if event == 'socket.connect':
            raise RuntimeError('CPU tokenizer network forbidden')
    sys.addaudithook(audit)
    raw = sys.stdin.buffer.read(24001)
    if len(raw) > 24000:
        raise ValueError('Message UTF-8 bound exceeded')
    messages = json.loads(raw)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True, trust_remote_code=False)
    encoded = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, enable_thinking=False)
    ids = encoded['input_ids'] if hasattr(encoded, 'keys') and 'input_ids' in encoded else encoded
    if ids and isinstance(ids[0], list):
        if len(ids) != 1:
            raise ValueError('Single input required')
        ids = ids[0]
    if not isinstance(ids, list) or not all(isinstance(token, int) for token in ids):
        raise ValueError('Expected input_ids token sequence')
    canonical = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    result = {'tokens': len(ids), 'canonical_messages_sha256': hashlib.sha256(canonical).hexdigest(),
              'template_sha256': hashlib.sha256(str(tokenizer.chat_template).encode()).hexdigest(),
              'source_hashes': {name: hashlib.sha256((MODEL/name).read_bytes()).hexdigest() for name in ['tokenizer.json', 'tokenizer_config.json']},
              'method': 'len(input_ids), CPU, no model weights', 'model_calls': 0}
    sys.stdout.write(json.dumps(result)+'\n')

if __name__ == '__main__':
    main()
