import numpy as np

# To generate data

# theta1 = 0.05*alpha
# theta2 = 0.15*alpha
# theta3 = 5
# theta4 = 0.05

# # R1
# def lambda1(params, x):
#     return 0.05*params[0]*(1-x[0])

# # R2
# def lambda2(params, x):
#     return 0.15*params[0]*x[0]

# # R3
# def lambda3(params, x):
#     return 5*x[0]

# # R4
# def lambda4(params, x):
#     return 0.05*x[1]

# Exact propensities:

# R1
def lambda1(params, x):
    return params[0]*(1-x[0])

# R2
def lambda2(params, x):
    return params[1]*x[0]

# R3
def lambda3(params, x):
    return params[2]*x[0]

# R4
def lambda4(params, x):
    return params[3]*x[1]


propensities = np.array([lambda1, lambda2, lambda3, lambda4])
stoich_mat = np.array([[1., 0.], [-1., 0.], [0., 1.], [0., -1.]]).T