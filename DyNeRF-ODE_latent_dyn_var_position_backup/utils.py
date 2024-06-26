import os
import numpy as np
from pathlib import Path

import torch
import random


def create_folder_ifnotexist(folder_path):
    folder_path = Path(folder_path)
    if not folder_path.exists():
        folder_path.mkdir(parents=True, exist_ok=False)
    return folder_path


class Tracker(object):
    
    def __init__(self):
        self.infos = {}
    
    def write_info(self, key, value):
        self.infos[key] = value
    
    def export_info(self):
        return self.infos
    
    def clean_info(self):
        self.infos = {}


def save_checkpoint(model, path):
    if not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    
    torch.save(model.state_dict(), path)


def load_checkpoint(model, path):
    model.load_state_dict(torch.load(path))


def denorm(x):
    """Convert the range from [-1, 1] to [0, 1]."""
    out = (x + 1) / 2
    return out.clamp_(0, 1)


def inf_generator(iterable):
    """Allows training with DataLoaders in a single infinite loop:
        for i, (x, y) in enumerate(inf_generator(train_loader)):
    """
    iterator = iterable.__iter__()
    while True:
        try:
            yield iterator.__next__()
        except StopIteration:
            iterator = iterable.__iter__()


def flatten(x, dim):
    return x.reshape(x.size()[:dim] + (-1,))


def get_device(tensor):
    device = torch.device("cpu")
    if tensor.is_cuda:
        device = tensor.get_device()
    return device

def get_data_dict(dataloader):
    data_dict = dataloader.__next__()
    return data_dict

def get_next_batch(data_dict, test_interp=False):

    device = get_device(data_dict["observed_data"])
    
    batch_dict = get_dict_template()
    
    # preserving values:
    batch_dict["mode"] = data_dict["mode"]
    
    batch_dict["observed_data"] = data_dict["observed_data"]
    #print(batch_dict["observed_data"].shape)
    batch_dict["observed_tp"] = data_dict["observed_tp"]
    #print(batch_dict["observed_tp"].shape)
    batch_dict["data_to_predict"] = data_dict["data_to_predict"]
    #print(batch_dict["data_to_predict"].shape)
    batch_dict["tp_to_predict"] = data_dict["tp_to_predict"]
    #print(batch_dict["tp_to_predict"].shape)
    batch_dict["poses"] = data_dict["poses"]
    #print(batch_dict["poses"].shape)
    batch_dict["poses_to_pred"] = data_dict["poses_to_pred"]
    #print(batch_dict["poses_to_pred"].shape)
    batch_dict["times"] = data_dict["times"]
    #print(batch_dict["times"].shape)
    batch_dict["times_to_pred"] = data_dict["times_to_pred"]
    #print(batch_dict["times_to_pred"].shape)
    #exit()
    
    # Input: Mask out skipped data
    if ("observed_mask" in data_dict) and (data_dict["observed_mask"] is not None):
        batch_dict["observed_mask"] = data_dict["observed_mask"]
        filter_mask = batch_dict["observed_mask"].unsqueeze(-1).unsqueeze(-1).to(device)
        
        if not test_interp:
            batch_dict["observed_data"] = filter_mask * batch_dict["observed_data"]
        else:
            selected_mask = batch_dict["observed_mask"].squeeze(-1).byte()
            b, t, c, h, w = batch_dict["observed_data"].size()
            batch_dict["observed_data"] = batch_dict["observed_data"][selected_mask, ...].view(b, t // 2, c, h, w)
            batch_dict["observed_mask"] = torch.ones(b, t // 2, 1).cuda()

    # Pred: Mask out skipped data
    if ("mask_predicted_data" in data_dict) and (data_dict["mask_predicted_data"] is not None):
        batch_dict["mask_predicted_data"] = data_dict["mask_predicted_data"]
        filter_mask = batch_dict["mask_predicted_data"].unsqueeze(-1).unsqueeze(-1).to(device)
        
        if not test_interp:
            batch_dict["orignal_data_to_predict"] = batch_dict["data_to_predict"].clone()
            # batch_dict["data_to_predict"] = filter_mask * batch_dict["data_to_predict"]
        else:
            b, t, c, h, w = batch_dict["data_to_predict"].size()
            # specify times
            batch_dict["tp_to_predict"] = torch.from_numpy(np.arange(0, t) / t).type(torch.FloatTensor).cuda()
            # mask out
            selected_mask = torch.ones_like(batch_dict["mask_predicted_data"]) - batch_dict["mask_predicted_data"]
            selected_mask[:, -1, :] = 0. # exclude last frame
            selected_mask = selected_mask.squeeze(-1).byte()
            batch_dict["mask_predicted_data"] = selected_mask

    if ("angle" in data_dict) and (data_dict["angle"] is not None):
        batch_dict["angle"] = data_dict["angle"]
        batch_dict["angle_to_pred"] = data_dict["angle_to_pred"]


    if "times_all" in data_dict:
        batch_dict["times_all"] = data_dict["times_all"]
    if "tp_all" in data_dict:
        batch_dict["tp_all"] = data_dict["tp_all"]
    if "win_start" in data_dict:
        batch_dict["win_start"] = data_dict["win_start"]
                                            
            
    return batch_dict


def update_learning_rate(optimizer, decay_rate=0.999, lowest=1e-3):
    for param_group in optimizer.param_groups:
        lr = param_group['lr']
        lr = max(lr * decay_rate, lowest)
        param_group['lr'] = lr

def reverse_time_order(tensor):
    idx = [i for i in range(tensor.size(1) - 1, -1, -1)]
    return tensor[:, idx, ...]


def get_dict_template():
    return {"observed_data": None,
            "observed_tp": None,
            "data_to_predict": None,
            "tp_to_predict": None,
            "observed_mask": None,
            "mask_predicted_data": None
            }


def split_data_extrap(data_dict, opt):
    
    #n_observed_tp = data_dict["data"].size(1) // 2
    n_observed_tp = 1
    # start_obs = random.randint(0, int(data_dict["data"].shape[1])-n_observed_tp-20)
    start_obs = 0
    # split_dict = {"observed_data": data_dict["data"][:, :n_observed_tp].clone(),
    #               "observed_tp": data_dict["time_steps"][:n_observed_tp].clone(),
    #               "data_to_predict": data_dict["data"][:, n_observed_tp:].clone(),
    #               "tp_to_predict": data_dict["time_steps"][n_observed_tp:].clone(),
    #               "tp_all": data_dict["time_steps"].clone(),
    #               "observed_mask": None, "mask_predicted_data": None}
    split_dict = {"observed_data": data_dict["data"][:, start_obs:start_obs+n_observed_tp].clone(),
                  "observed_tp": data_dict["time_steps"][start_obs:start_obs+n_observed_tp].clone(),
                  "data_to_predict": torch.cat((data_dict["data"][:, :start_obs].clone(), data_dict["data"][:, start_obs+n_observed_tp:].clone()), dim=1),
                #   "data_to_predict": data_dict["data"][:, start_obs+n_observed_tp:].clone(),
                  "tp_to_predict": torch.cat((data_dict["time_steps"][:start_obs].clone(), data_dict["time_steps"][start_obs+n_observed_tp:].clone()), dim=0),
                #   "tp_to_predict": data_dict["time_steps"][start_obs+n_observed_tp:].clone(),
                  "tp_all": data_dict["time_steps"].clone(),
                  "observed_mask": None, "mask_predicted_data": None}
    
    if ("mask" in data_dict) and (data_dict["mask"] is not None):
        split_dict["observed_mask"] = data_dict["mask"][:, :n_observed_tp].clone()
        split_dict["mask_predicted_data"] = data_dict["mask"][:, n_observed_tp:].clone()
    
    if ("poses" in data_dict) and (data_dict["poses"] is not None):
        # split_dict["poses"] = data_dict["poses"][:, :n_observed_tp].clone()
        # split_dict["poses_to_pred"] = data_dict["poses"][:, n_observed_tp:].clone()
        split_dict["poses"] = data_dict["poses"][:, start_obs:start_obs+n_observed_tp].clone()
        split_dict["poses_to_pred"] = torch.cat((data_dict["poses"][:, :start_obs].clone(), data_dict["poses"][:, start_obs+n_observed_tp:].clone()), dim=1)
        # split_dict["poses_to_pred"] = data_dict["poses"][:, start_obs+n_observed_tp:].clone()
    
    if ("times" in data_dict) and (data_dict["times"] is not None):
        # split_dict["times"] = data_dict["times"][:, :n_observed_tp].clone()
        # split_dict["times_to_pred"] = data_dict["times"][:, n_observed_tp:].clone()
        split_dict["times"] = data_dict["times"][:, start_obs:start_obs+n_observed_tp].clone()
        split_dict["times_to_pred"] = torch.cat((data_dict["times"][:, :start_obs].clone(), data_dict["times"][:, start_obs+n_observed_tp:].clone()), dim=1)
        # split_dict["times_to_pred"] = data_dict["times"][:, start_obs+n_observed_tp:].clone()
        split_dict["times_all"] = data_dict["times"].clone()

    if ("angle" in data_dict) and (data_dict["angle"] is not None): 
        split_dict["angle"] = data_dict["angle"][:, start_obs:start_obs+n_observed_tp].clone()
        split_dict["angle_to_pred"] = torch.cat((data_dict["angle"][:, :start_obs].clone(), data_dict["angle"][:, start_obs+n_observed_tp:].clone()), dim=1)

    #if ("win_start" in data_dict) and (data_dict["win_start"] is not None):
    split_dict["win_start"] = data_dict["win_start"]
    
    split_dict["mode"] = "extrap"
        
    return split_dict


def split_data_interp(data_dict, opt):

    split_dict = {"observed_data": data_dict["data"].clone(),
                  "observed_tp": data_dict["time_steps"].clone(),
                  "data_to_predict": data_dict["data"].clone(),
                  "tp_to_predict": data_dict["time_steps"].clone(),
                  "observed_mask": None,
                  "mask_predicted_data": None}

    if "mask" in data_dict and data_dict["mask"] is not None:
        split_dict["observed_mask"] = data_dict["mask"].clone()
        split_dict["mask_predicted_data"] = data_dict["mask"].clone()
    
    split_dict["mode"] = "interp"
    
    return split_dict


def add_mask(data_dict):
    data = data_dict["observed_data"]
    mask = data_dict["observed_mask"]
    
    if mask is None:
        mask = torch.ones_like(data).to(get_device(data))
    
    data_dict["observed_mask"] = mask
    return data_dict

def split_and_subsample_batch(data_dict, opt, data_type="train"):
    if data_type == "train":
        # Training set
        if opt.extrap:
            processed_dict = split_data_extrap(data_dict, opt)
        else:
            processed_dict = split_data_interp(data_dict, opt)
    
    else:
        # Test set
        if opt.extrap:
            processed_dict = split_data_extrap(data_dict, opt)
        else:
            processed_dict = split_data_interp(data_dict, opt)
    
    # add mask
    processed_dict = add_mask(processed_dict)
    
    return processed_dict