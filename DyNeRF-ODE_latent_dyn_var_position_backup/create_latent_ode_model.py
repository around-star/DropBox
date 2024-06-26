###########################
# Latent ODEs for Irregularly-Sampled Time Series
# Author: Yulia Rubanova
###########################

import os
import numpy as np

import torch
import torch.nn as nn
from torch.nn.functional import relu

import rnn_utils as utils
from latent_ode import LatentODE
from encoder_decoder import *
from diffeq_solver import DiffeqSolver

from torch.distributions.normal import Normal
from ode_func import ODEFunc, ODEFunc_w_Poisson
from run_dnerf_helpers import LatentNetwork, get_embedder

#####################################################################################################

def create_LatentODE_model(input_dim, z0_prior, obsrv_std, device, 
    classif_per_tp = False, n_labels = 1, latents=20, units=100, gen_layers=1,
    rec_layers=1, rec_dims=20, z0_encoder="odernn", gru_units=100, poisson=False, 
    num_frames=80, time_invariant=True):
    #latent_net = LatentNetwork(input_size=num_frames, latent_size=16)
    #self.latent_embedder, self.latent_embedder_out_dim = get_embedder(10, 16)
    #latent_embedder, latent_embedder_out_dim = get_embedder(10, 1)
    #latent_embedder, latent_embedder_out_dim = get_embedder(10, 1, include_input=False)
    #embed_angle, angle_dim = get_embedder(10, 1, 0)  ## For angle
    embed_angle, angle_dim = get_embedder(10, 3, 0)
    angle_linear_layer = nn.Linear(angle_dim, 21)
    angle_dim = 21
    latent_embedder_out_dim = angle_dim
    #latent_embedder_out_dim = 512
    #latent_embedder_out_dim = 64
    #latents = latent_embedder_out_dim
    print("Latent Embedder Size: ",latent_embedder_out_dim)
    input_dim = latent_embedder_out_dim
    dim = latent_embedder_out_dim

    if poisson:
        lambda_net = utils.create_net(dim, input_dim, 
            n_layers = 1, n_units = units, nonlinear = nn.Tanh)

        # ODE function produces the gradient for latent state and for poisson rate
        ode_func_net = utils.create_net(dim * 2, latents * 2, 
            n_layers = gen_layers, n_units = units, nonlinear = nn.Tanh)

        gen_ode_func = ODEFunc_w_Poisson(
            input_dim = input_dim, 
            latent_dim = latents * 2,
            ode_func_net = ode_func_net,
            lambda_net = lambda_net,
            device = device).to(device)
    else:
        #dim = latents ### OG Code
        latents_new = latent_embedder_out_dim
        dim = latents_new
        #print("Dim: ", dim)
        ode_func_net = utils.create_net(dim, latents_new, 
            n_layers = gen_layers, n_units = units, nonlinear = nn.Tanh)

        gen_ode_func = ODEFunc(
            input_dim = input_dim, 
            latent_dim = latents_new, 
            ode_func_net = ode_func_net,
            device = device).to(device)

    z0_diffeq_solver = None
    n_rec_dims = rec_dims
    #enc_input_dim = int(input_dim) * 2 # we concatenate the mask
    enc_input_dim = int(input_dim)
    gen_data_dim = input_dim

    z0_dim = latents
    if poisson:
        z0_dim += latents # predict the initial poisson rate

    """if z0_encoder == "odernn":
        ode_func_net = utils.create_net(n_rec_dims, n_rec_dims, 
            n_layers = rec_layers, n_units = units, nonlinear = nn.Tanh)

        rec_ode_func = ODEFunc(
            input_dim = enc_input_dim,
            latent_dim = n_rec_dims,
            ode_func_net = ode_func_net,
            device = device).to(device)

        z0_diffeq_solver = DiffeqSolver(enc_input_dim, rec_ode_func, "euler", latents, 
            odeint_rtol = 1e-3, odeint_atol = 1e-4, device = device)
        
        encoder_z0 = Encoder_z0_ODE_RNN(n_rec_dims, enc_input_dim, z0_diffeq_solver, 
            z0_dim = z0_dim, n_gru_units = gru_units, device = device).to(device)"""

    """elif z0_encoder == "rnn":
        encoder_z0 = Encoder_z0_RNN(z0_dim, enc_input_dim,
            lstm_output_size = n_rec_dims, device = device).to(device)"""
    #else:
    #    raise Exception("Unknown encoder for Latent ODE model: " + z0_encoder)

    decoder = Decoder(latents_new, 512).to(device)

    #diffeq_solver = DiffeqSolver(gen_data_dim, gen_ode_func, 'dopri5', latents, 
    #    odeint_rtol = 1e-3, odeint_atol = 1e-4, device = device)
    diffeq_solver = DiffeqSolver(gen_data_dim, gen_ode_func, 'euler', latents_new, 
        odeint_rtol = 1e-3, odeint_atol = 1e-4, device = device)
    
    model = LatentODE(
        input_dim = gen_data_dim, 
        latent_dim = latents, 
        encoder_z0 = None, 
        decoder = decoder, 
        diffeq_solver = diffeq_solver,
        z0_prior = z0_prior, 
        device = device,
        obsrv_std = obsrv_std,
        use_poisson_proc = poisson, 
        use_binary_classif = False,
        linear_classifier = False,
        classif_per_tp = classif_per_tp,
        n_labels = n_labels,
        train_classif_w_reconstr = False,
        num_frames=num_frames,
        latent_embedder_out_dim = latent_embedder_out_dim,
        latent_embedder = None,
        embed_angle = embed_angle,
        angle_linear_layer = angle_linear_layer
        ).to(device)

    return model