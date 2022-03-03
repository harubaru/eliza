from shimeji.model_provider import ModelProvider, Sukima_ModelProvider, ModelGenRequest, ModelGenArgs, ModelSampleArgs, ModelLogitBiasArgs, ModelPhraseBiasArgs
import argparse
import json

def parse():
    parser = argparse.ArgumentParser(
        description="Eliza is a configurable open-domain chatbot.",
        usage="eliza [arguments]",
    )

    parser.add_argument(
        '-c', '--config',
        help="Path to the config file.",
        type=str,
        required=True
    )

    return parser.parse_args()

def config(args):
    with open(args.config) as f:
        return json.load(f)

def get_item(obj, key):
    if key in obj:
        return obj[key]
    else:
        return None

def get_model_provider(args):
    # load model provider gen_args into basemodel
    if 'model_provider' not in args:
        raise Exception('model_provider is not specified in config file.')
    if args["model_provider"]["name"] == "sukima":
        gen_args = ModelGenArgs(
            max_length=get_item(args["model_provider"]["gensettings"]["gen_args"], "max_length"),
            max_time=get_item(args["model_provider"]["gensettings"]["gen_args"], "max_time"),
            min_length=get_item(args["model_provider"]["gensettings"]["gen_args"], "min_length"),
            eos_token_id=get_item(args["model_provider"]["gensettings"]["gen_args"], "eos_token_id"),
            logprobs=get_item(args["model_provider"]["gensettings"]["gen_args"], "logprobs"),
        )
        # logit biases are an array in args['model_provider']['gensettings']['logit_biases']
        logit_biases = None
        if 'logit_biases' in args["model_provider"]["gensettings"]["sample_args"]:
            logit_biases = [ModelLogitBiasArgs(
                id=logit_bias["id"],
                bias=logit_bias["bias"]
            ) for logit_bias in args["model_provider"]["gensettings"]["sample_args"]["logit_biases"]]
        # phrase biases are an array in args['model_provider']['gensettings']['phrase_biases']
        phrase_biases = None
        if 'phrase_biases' in args["model_provider"]["gensettings"]["sample_args"]:
            phrase_biases = [ModelPhraseBiasArgs(
                sequences=phrase_bias["sequences"],
                bias=phrase_bias["bias"],
                ensure_sequence_finish=phrase_bias["ensure_sequence_finish"],
                generate_once=phrase_bias["generate_once"]
            ) for phrase_bias in args["model_provider"]["gensettings"]["sample_args"]["phrase_biases"]]
        
        sample_args = ModelSampleArgs(
            temp=get_item(args["model_provider"]["gensettings"]["sample_args"], "temp"),
            top_p=get_item(args["model_provider"]["gensettings"]["sample_args"], "top_p"),
            top_a=get_item(args["model_provider"]["gensettings"]["sample_args"], "top_a"),
            top_k=get_item(args["model_provider"]["gensettings"]["sample_args"], "top_k"),
            typical_p=get_item(args["model_provider"]["gensettings"]["sample_args"], "typical_p"),
            tfs=get_item(args["model_provider"]["gensettings"]["sample_args"], "tfs"),
            rep_p=get_item(args["model_provider"]["gensettings"]["sample_args"], "rep_p"),
            rep_p_range=get_item(args["model_provider"]["gensettings"]["sample_args"], "rep_p_range"),
            rep_p_slope=get_item(args["model_provider"]["gensettings"]["sample_args"], "rep_p_slope"),
            bad_words=get_item(args["model_provider"]["gensettings"]["sample_args"], "bad_words"),
            logit_biases=logit_biases,
            phrase_biases=phrase_biases
        )

        request = ModelGenRequest(
            model=args["model_provider"]["gensettings"]["model"],
            prompt='',
            sample_args=sample_args,
            gen_args=gen_args
        )

        return Sukima_ModelProvider(
            endpoint_url=args["model_provider"]["endpoint"],
            username=args["model_provider"]["username"],
            password=args["model_provider"]["password"],
            args=request
        )
    else:
        raise Exception('model_provider is not supported.')