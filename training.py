import convert_csv
import neuralnetwork
import simulation
from CRN2_production_degradation import propensities_production_degradation as propensities
import numpy as np
import save_load_MDN
import torch

FILE_NAME = 'CRN2_production_degradation/data'
NAME = 'production_degradation'

N_PARAMS = 2

X_train = convert_csv.csv_to_tensor(f'{FILE_NAME}/X_{NAME}_train1.csv')
y_train = convert_csv.csv_to_tensor(f'{FILE_NAME}/y_{NAME}_train1.csv')
X_valid = convert_csv.csv_to_tensor(f'{FILE_NAME}/X_{NAME}_valid1.csv')
y_valid = convert_csv.csv_to_tensor(f'{FILE_NAME}/y_{NAME}_valid1.csv')
X_test = convert_csv.csv_to_tensor(f'{FILE_NAME}/X_{NAME}_test.csv')
y_test = convert_csv.csv_to_tensor(f'{FILE_NAME}/y_{NAME}_test.csv')

data_train = [X_train, y_train]
data_valid = [X_valid, y_valid]
data_test = [X_test, y_test]

LR = 0.005
N_ITER  = 700
BATCHSIZE = 32
N_HIDDEN = 256
MIXTURE = 'NB'
N_COMPS = 4
PATIENCE = 60
DELTA = 1e-5

crn = simulation.CRN(propensities.stoich_mat, propensities.propensities, init_state=propensities.init_state, n_fixed_params=N_PARAMS, n_control_params=0)
model = neuralnetwork.NeuralNetwork(n_comps=N_COMPS, n_params=N_PARAMS, n_hidden=N_HIDDEN, mixture=MIXTURE)
trainer_test = neuralnetwork.train_NN(model, data_train, data_valid, loss=neuralnetwork.loss_kldivergence, max_rounds=N_ITER, lr=LR, batchsize=BATCHSIZE)

save_load_MDN.save_MDN_model(model, 'new_loss_model.pt')
torch.save({'train_losses': trainer_test[0], 'valid_losses': trainer_test[1]}, 'losses.pt')

print(trainer_test[0], trainer_test[1])

print("Training dataset")
print(f"KLD : {neuralnetwork.mean_loss(X_train, y_train, model, loss=neuralnetwork.loss_kldivergence)}")
print(f'Hellinger : {neuralnetwork.mean_loss(X_train, y_train, model, loss=neuralnetwork.loss_hellinger)}')

print("\nValidation dataset")
print(f"KLD : {neuralnetwork.mean_loss(X_valid, y_valid, model, loss=neuralnetwork.loss_kldivergence)}")
print(f'Hellinger : {neuralnetwork.mean_loss(X_valid, y_valid, model, loss=neuralnetwork.loss_hellinger)}')

print("\nTest dataset")
print(f"KLD : {neuralnetwork.mean_loss(X_test, y_test, model, loss=neuralnetwork.loss_kldivergence)}")
print(f'Hellinger : {neuralnetwork.mean_loss(X_test, y_test, model, loss=neuralnetwork.loss_hellinger)}')