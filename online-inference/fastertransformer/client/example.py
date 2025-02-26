import json
import torch
import numpy as np
import tritonclient.grpc as grpcclient
import tritonclient.http as httpclient

from argparse import ArgumentParser
from collections.abc import Mapping
from tritonclient.utils import np_to_triton_dtype

import os
import sys

# GPT_BPE Tokenizer
import gpt_bpe.gpt_token_encoder as encoder

merge_file = "/workspace/gpt_bpe/gpt2-merges.txt"
vocab_file = "/workspace/gpt_bpe/gpt2-vocab.json"
enc = encoder.get_encoder(vocab_file, merge_file)

# HFTokenizer
from hf_tokenizer.hf_tokenize import HFTokenizer 

hf_encoder_vocab_file = "/workspace/hf_tokenizer/20B_tokenizer.json"
hf_enc = HFTokenizer(vocab_file=hf_encoder_vocab_file)

def deep_update(source, overrides):
    """
    Update a nested dictionary or similar mapping.
    Modify ``source`` in place.
    """
    for key, value in overrides.items():
        if isinstance(value, Mapping) and value:
            returned = deep_update(source.get(key, {}), value)
            source[key] = returned
        else:
            source[key] = overrides[key]
    return source

def encode_data(model, text):
    if model == "gptj":
        all_ids = [torch.IntTensor(enc.encode(text))]
    elif model == "gpt-neox":
        all_ids = [torch.IntTensor(hf_enc.tokenize(text))]
    return all_ids[0].numpy()


def decode_data(array, model):
    if model == "gptj":
        sentence = enc.decode(array)
    elif model == "gpt-neox":
        sentence = hf_enc.detokenize(array)
    return sentence

def generate_parameters(args):
    DEFAULT_CONFIG = {
        'protocol': 'http',
        'url': f'{args.url}:80',
        'model_name': 'fastertransformer',
        'verbose': False,
    }

    params = {'config': DEFAULT_CONFIG}

    with open('/workspace/sample_request.json') as f:
        file_params = json.load(f)

    deep_update(params, file_params)

    input_lengths = len(encode_data(text=args.prompt, model=args.model))

    for index, value in enumerate(params['request']):
        if value['name'] == 'input_ids':
            value['data'] = [encode_data(model=args.model, text=args.prompt)] 
        if value['name'] == 'input_lengths':
            value['data'] = [[input_lengths]]
        params['request'][index] = {
            'name': value['name'],
            'data': np.array(value['data'], dtype=value['dtype']),
        }
    

    return params['config'], params['request']


def prepare_tensor(client, name, input):
    t = client.InferInput(name, input.shape, np_to_triton_dtype(input.dtype))
    t.set_data_from_numpy(input)
    return t


def main(config, request):
    client_type = httpclient if config['protocol'] == 'http' else grpcclient
    with client_type.InferenceServerClient(config['url'], verbose=config['verbose'], concurrency=1, connection_timeout=100.0, network_timeout=100.0,) as cl:
        payload = [prepare_tensor(client_type, field['name'], field['data'])
            for field in request]

        result = cl.infer(config['model_name'], payload)

    for output in result.get_response()['outputs']:
        if output['name'] == "output_ids":
            print(f"Ouput: {decode_data(list(result.as_numpy(output['name'])[0][0]), model=args.model)}")

def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--url", help="InferenceService URL for Fastertransfomer", required=True)
    parser.add_argument("--prompt", help="Prompt to generate based of.", required=True)
    parser.add_argument("--model", help="gptj or gpt-neox", required=True)
    
    args = parser.parse_args()

    return args

if __name__ == "__main__":
    args = parse_args()
    config, request = generate_parameters(args)
    main(config, request)