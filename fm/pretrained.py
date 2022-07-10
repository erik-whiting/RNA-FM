# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import fm
import torch
from argparse import Namespace
import warnings
import urllib
from pathlib import Path

def load_model_and_alphabet(model_name):
    if model_name.endswith(".pt"):  # treat as filepath
        return load_model_and_alphabet_local(model_name)
    else:
        return load_model_and_alphabet_hub(model_name)

def load_hub_workaround(url):
    try:
        data = torch.hub.load_state_dict_from_url(url, progress=False, map_location='cpu')
    except RuntimeError:
        # Pytorch version issue - see https://github.com/pytorch/pytorch/issues/43106
        fn = Path(url).name
        data = torch.load(
            f"{torch.hub.get_dir()}/checkpoints/{fn}",
            map_location="cpu",
        )
    return data


def load_regression_hub(model_name):
    url = f"https://dl.fbaipublicfiles.com/fair-esm/regression/{model_name}-contact-regression.pt"
    regression_data = load_hub_workaround(url)
    return regression_data

def load_model_and_alphabet_hub(model_name, theme="protein"):
    url = f"https://dl.fbaipublicfiles.com/fair-esm/models/{model_name}.pt"
    model_data = load_hub_workaround(url)
    regression_data = load_regression_hub(model_name)
    return load_model_and_alphabet_core(model_data, regression_data, theme)

def load_model_and_alphabet_local(model_location, theme="protein"):
    """ Load from local path. The regression weights need to be co-located """
    model_data = torch.load(model_location, map_location='cpu')
    try:
        regression_location = model_location[:-3] + "-contact-regression.pt"
        regression_data = torch.load(regression_location, map_location='cpu')
    except FileNotFoundError:
        regression_data = None
    return load_model_and_alphabet_core(model_data, regression_data, theme)

def load_model_and_alphabet_core(model_data, regression_data=None, theme="protein"):
    if regression_data is not None:
        model_data["model"].update(regression_data["model"])

    alphabet = fm.Alphabet.from_architecture(model_data["args"].arch, theme=theme)

    if model_data["args"].arch == 'roberta_large':
        # upgrade state dict
        pra = lambda s: ''.join(s.split('encoder_')[1:] if 'encoder' in s else s)
        prs1 = lambda s: ''.join(s.split('encoder.')[1:] if 'encoder' in s else s)
        prs2 = lambda s: ''.join(s.split('sentence_encoder.')[1:] if 'sentence_encoder' in s else s)
        model_args = {pra(arg[0]): arg[1] for arg in vars(model_data["args"]).items()}
        model_state = {prs1(prs2(arg[0])): arg[1] for arg in model_data["model"].items()}
        model_state["embed_tokens.weight"][alphabet.mask_idx].zero_()  # For token drop
        model_type = fm.ProteinBertModel
    elif model_data["args"].arch == 'protein_bert_base':

        # upgrade state dict
        pra = lambda s: ''.join(s.split('decoder_')[1:] if 'decoder' in s else s)
        prs = lambda s: ''.join(s.split('decoder.')[1:] if 'decoder' in s else s)
        model_args = {pra(arg[0]): arg[1] for arg in vars(model_data["args"]).items()}
        model_state = {prs(arg[0]): arg[1] for arg in model_data["model"].items()}
        model_type = fm.ProteinBertModel
    elif model_data["args"].arch == 'msa_transformer':

        # upgrade state dict
        pra = lambda s: ''.join(s.split('encoder_')[1:] if 'encoder' in s else s)
        prs1 = lambda s: ''.join(s.split('encoder.')[1:] if 'encoder' in s else s)
        prs2 = lambda s: ''.join(s.split('sentence_encoder.')[1:] if 'sentence_encoder' in s else s)
        prs3 = lambda s: s.replace("row", "column") if "row" in s else s.replace("column", "row")
        model_args = {pra(arg[0]): arg[1] for arg in vars(model_data["args"]).items()}
        model_state = {prs1(prs2(prs3(arg[0]))): arg[1] for arg in model_data["model"].items()}

        model_type = fm.MSATransformer

    else:
        raise ValueError("Unknown architecture selected")

    model = model_type(
        Namespace(**model_args), alphabet,
    )

    expected_keys = set(model.state_dict().keys())
    found_keys = set(model_state.keys())

    if regression_data is None:
        expected_missing = {"contact_head.regression.weight", "contact_head.regression.bias"}
        error_msgs = []
        missing = (expected_keys - found_keys) - expected_missing
        if missing:
            error_msgs.append(f"Missing key(s) in state_dict: {missing}.")
        unexpected = found_keys - expected_keys
        if unexpected:
            error_msgs.append(f"Unexpected key(s) in state_dict: {unexpected}.")

        if error_msgs:
            raise RuntimeError("Error(s) in loading state_dict for {}:\n\t{}".format(
                model.__class__.__name__, "\n\t".join(error_msgs)))
        if expected_missing - found_keys:
            warnings.warn("Regression weights not found, predicting contacts will not produce correct results.")

    model.load_state_dict(model_state, strict=regression_data is not None)

    return model, alphabet

def esm1_t34_670M_UR50S_local():
    model_location = '/checkpoint/bioseq_nonsecure/br2020/br4/checkpoint94.pt'
    model, alphabet = load_model_and_alphabet_local(model_location)

    return model, alphabet

def esm1_t34_670M_UR50S_hub():
    return load_model_and_alphabet_hub("esm1_t34_670M_UR50S")

def esm1_t34_670M_UR50S():
    """ 34 layer transformer model with 670M params, trained on Uniref50 Sparse.

    Returns a tuple of (Model, Alphabet).
    """
    return load_model_and_alphabet_hub("esm1_t34_670M_UR50S")

def esm1_t34_670M_UR50D():
    """ 34 layer transformer model with 670M params, trained on Uniref50 Dense.

    Returns a tuple of (Model, Alphabet).
    """
    return load_model_and_alphabet_hub("esm1_t34_670M_UR50D")

def esm1_t34_670M_UR100():
    """ 34 layer transformer model with 670M params, trained on Uniref100.

    Returns a tuple of (Model, Alphabet).
    """
    return load_model_and_alphabet_hub("esm1_t34_670M_UR100")

def esm1_t12_85M_UR50S():
    """ 12 layer transformer model with 85M params, trained on Uniref50 Sparse.

    Returns a tuple of (Model, Alphabet).
    """
    return load_model_and_alphabet_hub("esm1_t12_85M_UR50S")

def esm1_t6_43M_UR50S():
    """ 6 layer transformer model with 43M params, trained on Uniref50 Sparse.

    Returns a tuple of (Model, Alphabet).
    """
    return load_model_and_alphabet_hub("esm1_t6_43M_UR50S")

def esm1b_t33_650M_UR50S():
    """ 33 layer transformer model with 650M params, trained on Uniref50 Sparse.
    This is our best performing model, which will be described in a future publication.

    Returns a tuple of (Model, Alphabet).
    """
    return load_model_and_alphabet_hub("esm1b_t33_650M_UR50S")

def esm_msa1_t12_100M_UR50S():
    return load_model_and_alphabet_hub("esm_msa1_t12_100M_UR50S")


# CJY for RNA
def esm1b_rna_t12():
    # KAUST
    #model_location = "/ibex/scratch/liy0f/cjy/projects/PretrainBioLM/work_space/RNAcentral/checkpoints/checkpoint_best.pt"

    # SZ-gpu
    # scp dgxadmin@120.204.84.133:/raid/databases/chenjiayang/PretrainedModel/RNAcentral/checkpoint_best.pt /share/liyu/RNA/PretrainedModels/RNAcentral/
    # scp dgxadmin@120.204.84.133:/home/dgxadmin/chenjy/PretrainBioLM/work_space/RNAcentral/checkpoints/checkpoint_best.pt /share/liyu/RNA/PretrainedModels/RNAcentral/
    #model_location = "/share/liyu/RNA/PretrainedModels/RNAcentral/checkpoint_best.pt"

    # CUHK-150
    # scp dgxadmin@120.204.84.133:/raid/databases/chenjiayang/PretrainedModel/RNAcentral/* /data/chenjiayang/projects/Model/RNAcentral/
    # scp dgxadmin@120.204.84.133:/raid/databases/chenjiayang/PretrainedModel/RNAcentral/checkpoint_best.pt E:/Dataset/PretrainModel
    #model_location = "/data/chenjiayang/projects/Model/bpRNA-90/checkpoint_best.pt"        # 150
    #model_location = "/data/chenjiayang/projects/Model/RNAcentral/checkpoint_best.pt"      # 150
    #model_location = "/data/chenjiayang/projects/Model/Toehold-Switch/checkpoint_best.pt"   # 150

    # A100
    # cp /home/dgxadmin/chenjy/PretrainBioLM/work_space/RNAcentral/checkpoints/* /raid/databases/chenjiayang/PretrainedModel/RNAcentral
    #model_location = "/raid/databases/chenjiayang/PretrainedModel/RNAcentral/checkpoint_best.pt"

    # local
    model_location = "./pretrained/RNA-FM_pretrained.pth"

    return load_model_and_alphabet_local(model_location, theme="rna")
