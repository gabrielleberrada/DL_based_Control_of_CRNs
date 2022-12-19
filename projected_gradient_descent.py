import numpy as np
import casadi
import matplotlib.pyplot as plt
import torch
import get_sensitivities
import neuralnetwork
import simulation
import generate_data
import fsp
import plot
import collections.abc as abc
from typing import Callable, Union
import time
from tqdm import tqdm

class ProjectedGradientDescent():
    """Class to compute the Projected Gradient Descent Algorithm.

    Args:
        - *grad_loss** (Callable): Gradient of the loss.
        - *domain** (np.ndarray): Boundaries of the domain to project in. Shape :math:`(dim, 2)`.
            `domain[:,0]` defines the lower boundaries for each dimension, `domain[:,1]` defines the 
            upper boundaries for each dimension.
        - *dim** (int): Number of dimensions of the considered space.
    """
    def __init__(self, grad_loss: Callable, domain: np.ndarray, dim: int):
        self.grad_loss = grad_loss
        self.domain = domain
        self.dim = dim


    def projected_gradient_descent(self,
                                init: np.ndarray,
                                gamma: float,
                                n_iter: int =1_000,
                                tolerance: float =1e-3,
                                tolerance_rounds: int =1_000,
                                norm: Callable =casadi.norm_2,
                                progress_bar: bool =True # pour afficher la progress bar
                                ):
        """_summary_

        Args:
            - **init** (np.ndarray): Initial state for the controlled parameters. Has shape N_t*n_control_params.
            - **gamma** (float): Step size.
            - **n_iter** (int, optional): Number of iterations for the gradient descent. 
              Defaults to :math:`1000`.
            - **tolerance** (float, optional): Tolerance rate. Defaults to :math:`10^{-20}`.
            - **tolerance_rounds** (int, optional): Number of rounds allowed without improvement before stopping
              the gradient descent. Defaults to :math:`20`.
            - **norm** (Callable, optional): Norm to use for the optimization. Defaults to `casadi.norm_2`.

        Returns:
            _type_: _description_
        """   
        xt = [init]
        losses = []
        if progress_bar:
            pbar = tqdm(total=n_iter, desc = 'Optimizing ...', position=0)
        for i in range(n_iter):
            if progress_bar:
                pbar.update(1)
            x = xt[-1] - gamma*self.grad_loss(xt[-1])
            for n in range(self.dim):
                x[n] = min(x[n], self.domain[n, 1])
                x[n] = max(x[n], self.domain[n, 0])
            print(np.linalg.norm(self.grad_loss(xt[-1]))**2)
            if np.linalg.norm(self.grad_loss(xt[-1]))**2 <= tolerance:
                break
            xt.append(x)
            losses.append(self.loss(x))
            if np.argmin(losses[-tolerance_rounds:]) == 0:
                gamma = gamma/2
                print('Updating gamma at iteration', i, 'to value', gamma)
                if gamma < 1e-5:
                    break
            # to check
            # method 1
            # if i >= tolerance_rounds:
            #     last_elts = np.array(xt[-tolerance_rounds:])
            #     last_elts[0] -= tolerance
            #     if np.argmin(last_elts) == 0:
            #         break
            # method 2
            # if i >= tolerance_rounds and np.all(np.abs(losses) <= tolerance):
        if progress_bar:
            pbar.close()
        return np.array(xt), np.array(losses) # xt has shape (n_iter, dim)

class ProjectedGradientDescent_CRN(ProjectedGradientDescent):
    def __init__(self,
                domain: np.ndarray,
                fixed_params: np.ndarray,
                time_windows: np.ndarray):
        self.domain = domain
        self.fixed_parameters = fixed_params
        self.n_fixed_params = len(fixed_params)
        self.init_control_params = np.random.uniform(self.domain[:, 0], self.domain[:, 1])
        self.dim = len(self.init_control_params)
        self.time_windows = time_windows
        self.n_time_windows = len(time_windows)
        self.n_control_params = self.dim // self.n_time_windows

    def optimisation(self, gamma: float, n_iter: int =1_000, tolerance: float =1e-20, tolerance_rounds: int =20, norm: Callable =casadi.norm_2):
        """_summary_

        Args:
            - **gamma** (float): Step size.
            - **n_iter** (int): Number of iterations for the gradient descent. Defaults to :math:`1000`.
            - **tolerance** (int): Tolerance rate. Defaults to :math:`10^{-20}`.
            - **tolerance_rounds** (float): Number of rounds allowed without improvements before stopping the gradient descent.
              Defaults to :math:`20`.
            - **norm** (Callable): Norm to use for the optimisation. Defaults to `casadi.norm_2`.
        """        
        self.buffer_params, self.buffer_losses = self.projected_gradient_descent(self.init_control_params, gamma, n_iter, tolerance, tolerance_rounds, norm)
        return self.buffer_params[-1], self.buffer_losses[-1]
    
    def plot_control_values(self):
        edges = np.concatenate(([0], self.time_windows))
        plt.stairs(self.buffer_params[-1,:], edges, baseline=None)
        plt.ylim(plt.ylim()[0]-0.1, plt.ylim()[1])
        plt.ylabel('Parameter value')
        plt.xlabel('Time')
        plt.title('Control parameters')
        plt.show()
    
    def plot_losses_trajectory(self):
        plt.plot(self.buffer_losses)
        plt.xlabel('Iterations')
        plt.ylabel('Loss value')
        plt.title('Losses')
        plt.show()

    def plot_control_params_trajectory(self):
        for i in range(self.n_control_params):
            for j in range(self.n_time_windows):
                plt.plot(self.buffer_params[:,i+j*self.n_control_params], label=fr'$\xi_{i+1}^{j+1}$')
        plt.ylim(plt.ylim()[0]-0.1, plt.ylim()[1]+0.1)
        plt.legend()
        plt.show()




class ProjectedGradientDescent_MDN(ProjectedGradientDescent_CRN):
    """_summary_

    Args:
        - **model** (neuralnetwork.NeuralNetwork): Model used for the gradient descent.
        - **domain** (np.ndarray): Allowed interval for each controlled parameter.
        - **fixed_params** (np.ndarray): Values of the fixed parameters.
        - **time_windows** (np.ndarray): Time windows.
        - **cost** (Callable): Cost function.
        - **init_control_params** (np.ndarray): Initial values of the controlled parameters. Must all be non zeros.
        - **length_output** (int): 
        - **with_correction** (bool, optional): If True, sensitivities are set to zero when controlled parameters
            have no influence on that time window. If False, lets the computed sensitivities. Defaults to True.
    """ 
    def __init__(self, 
                model:neuralnetwork.NeuralNetwork, 
                domain: np.ndarray, 
                fixed_params: np.ndarray,
                time_windows: np.ndarray, 
                cost: Union[Callable, list],
                weights: np.ndarray =None,
                length_output: int =200, 
                with_correction: bool =True):  
        super().__init__(domain, fixed_params, time_windows)     
        self.model = model
        self.create_gradient(cost, length_output, weights, with_correction)
        self.create_loss(cost, length_output, weights)

    def create_gradient(self, cost: Callable, length_output: int, weights: np.ndarray, with_correction: bool):
        """_summary_

        Args:
            - **time_windows** (np.ndarray): Time windows.
            - **cost** (Callable): Cost function.
            - **length_output** (int):
            - **with_correction** (bool): If True, sensitivities are set to zero when controlled parameters
              have no influence on that time window. If False, lets the computed sensitivities. Defaults to True.
        """
        if weights is None:
            weights = np.ones(self.n_time_windows)
        if isinstance(cost, abc.Hashable):
            cost = [cost]*self.n_time_windows  
        if with_correction:
            def grad_loss(control_params):
                res = np.zeros(self.dim)
                params = np.concatenate((self.fixed_parameters, control_params))
                for i, t in enumerate(self.time_windows):
                    inputs = np.concatenate(([t], params))
                    grad_exp = get_sensitivities.gradient_expected_val(inputs=torch.tensor(inputs, dtype=torch.float32), model=self.model, loss=cost[i], length_output=length_output)[1+self.n_fixed_params:]
                    grad_exp[(i+1)*self.n_control_params:] = 0 # these parameters have no influence on this time window
                    res += weights[i]*grad_exp
                return res
        else:
            def grad_loss(control_params):
                res = 0
                params = np.concatenate((self.fixed_parameters, control_params))
                for i, t in enumerate(self.time_windows):
                    inputs = np.concatenate(([t], params))
                    res += weights[i]*get_sensitivities.gradient_expected_val(inputs=torch.tensor(inputs, dtype=torch.float32), model=self.model, loss=cost[i], length_output=length_output)[1+self.n_fixed_params:]
                return res
        self.grad_loss = grad_loss

    def create_loss(self, cost: Callable, length_output: int, weights: np.ndarray):
        if weights is None:
            weights = np.ones(self.n_time_windows)
        if isinstance(cost, abc.Hashable):
            cost = [cost]*self.n_time_windows
        def loss(control_params):
            params = np.concatenate((self.fixed_parameters, control_params))
            loss_value = 0
            for i, t in enumerate(self.time_windows):
                inputs = np.concatenate(([t], params))
                loss_value += weights[i]*get_sensitivities.expected_val(inputs=torch.tensor(inputs, dtype=torch.float32), model=self.model, loss=cost[i], length_output=length_output)
            return loss_value
        self.loss = loss


class ProjectedGradientDescent_FSP(ProjectedGradientDescent_CRN):
    def __init__(self,
                crn: simulation.CRN,
                ind_species: int,
                domain: np.ndarray,
                fixed_params: np.ndarray,
                time_windows: np.ndarray,
                cost: Callable,
                grad_cost: Callable,
                cr: int):
        super().__init__(domain, fixed_params, time_windows)
        self.crn = crn
        self.ind_species = ind_species
        self.stv_calculator = fsp.SensitivitiesDerivation(self.crn, self.n_time_windows, index=None, cr=cr)
        self.create_gradient(grad_cost)
        self.create_loss(cost)

    def create_loss(self, cost: Callable):
        def loss(control_params):
            fixed_parameters = np.stack([self.fixed_parameters]*self.n_time_windows)
            control_parameters = control_params.reshape(self.n_time_windows, self.n_control_params)
            params = np.concatenate((fixed_parameters, control_parameters), axis=1)
            res= self.stv_calculator.expected_val(sampling_times=self.time_windows, 
                                                    time_windows=self.time_windows, 
                                                    parameters=params, 
                                                    ind_species=self.ind_species, 
                                                    loss=cost)
            return res.sum()
        self.loss = loss

    def create_gradient(self, grad_cost: Callable):
        def grad_loss(control_params):
            fixed_parameters = np.stack([self.fixed_parameters]*self.n_time_windows)
            control_parameters = control_params.reshape(self.n_time_windows, self.n_control_params)
            params = np.concatenate((fixed_parameters, control_parameters), axis=1)
            gradient= self.stv_calculator.gradient_expected_val(sampling_times=self.time_windows,
                                                            time_windows=self.time_windows,
                                                            parameters=params,
                                                            ind_species=self.ind_species,
                                                            loss=identity)[:,self.n_fixed_params:]
            expec = self.stv_calculator.expected_val(sampling_times=self.time_windows,
                                                    time_windows=self.time_windows,
                                                    parameters=params,
                                                    ind_species=self.ind_species)
            return grad_cost(expec, gradient).sum(axis=0)
        self.grad_loss = grad_loss

    
# testing for MDNs
if __name__ == '__main__':

    def identity(x):
        return x

    # def cost(x):
    #     return (x-3)**2

    def cost1(x):
        return (x-3)**2

    def cost2(x):
        return (x-2)**2

    def cost3(x):
        return (x-1)**2

    def cost4(x):
        return x**2

    # def grad_cost(probs, stv):
    #     return 2*stv*(probs-2)


    from CRN2_control import propensities_production_degradation as propensities
    crn = simulation.CRN(propensities.stoich_mat, propensities.propensities, propensities.init_state, 1, 1)
    domain = np.stack([np.array([1e-10, 4.])]*4)
    fixed_params = np.array([2.])
    time_windows=np.array([5, 10, 15, 20])

    # MDN
    import save_load_MDN
    model = save_load_MDN.load_MDN_model('CRN2_control/saved_models/CRN2_model1.pt')

    optimizer = ProjectedGradientDescent_MDN(model=model, 
                                            domain=domain, 
                                            fixed_params=fixed_params,
                                            time_windows=time_windows,
                                            cost=[cost1, cost2, cost3, cost4],
                                            weights=None)
    # print('MDN')
    # print(optimizer.loss(optimizer.init_control_params))
    # print(optimizer.grad_loss(optimizer.init_control_params))
    # plot.multiple_plots(to_pred=[torch.tensor([k, 2., 1.34, 1.34, 1.34, 1.34]) for k in [5., 10., 15., 20.]], 
    #                     models=[model], 
    #                     up_bound=4*[30],
    #                     time_windows=np.array([5, 10, 15, 20]),
    #                     n_comps=4,
    #                     index_names = ('Sensitivities', r'Abundance of species $S$'),
    #                     plot_exact_result=(False, None),
    #                     plot_fsp_result=(True, propensities.stoich_mat, propensities.propensities, 30, propensities.init_state, 0, 1, 1),
    #                     )
    # plt.show()

    # FSP
    # optimizer = ProjectedGradientDescent_FSP(crn=crn, 
    #                                         ind_species=propensities.ind_species, 
    #                                         domain=domain, 
    #                                         fixed_params=fixed_params, 
    #                                         time_windows=time_windows, 
    #                                         cost=cost,
    #                                         grad_cost=grad_cost,
    #                                         cr=50)
    # print('FSP')
    # print(optimizer.loss(optimizer.init_control_params))
    # print(optimizer.grad_loss(optimizer.init_control_params))

    # # Exact loss
    # def exact_gradient_loss(t, theta1, theta2):
    #     lambd = theta1/theta2*(1-np.exp(-theta2*t))
    #     # return lambd*(t*np.exp(-theta2*t) - 1/theta2)*(2*lambd - 2*2+1)
    #     return 2*(lambd-2)*theta1/theta2*(-(t-np.exp(-theta2*t))/theta2 + t*theta1/theta2*np.exp(-theta2*t))

    # def exact_loss(t, theta1, theta2):
    #     lambd = theta1/theta2*(1-np.exp(-theta2*t))
    #     # return lambd*(lambd+1-2*2) + 2**2
    #     return (lambd -2)**2

    # def f(theta1, theta2):
    #     res = 0
    #     for t in time_windows:
    #         res += exact_gradient_loss(t, theta1, theta2)
    #     return res

    # # stv = fsp.SensitivitiesDerivation(crn, 1, 1, cr=50)
    # # x1 = []
    # x2 = []
    # x3 = []
    # for elt in np.linspace(0.2, 2, 50):
    #     fixed_parameters = np.stack([np.array([2.])]*4)
    #     control_parameters = np.array([elt]*4).reshape(4,1)
    #     params = np.concatenate((fixed_parameters, control_parameters), axis=1)
    #     # x1.append(stv.expected_val(np.array([5]), np.array([20]), params, 0, loss=cost))
    #     x3.append(optimizer.grad_loss(np.array([elt]*4))[2])
    #     # res = 0
    #     # for t in time_windows:
    #     #     res += get_sensitivities.gradient_expected_val(torch.tensor([t, 2., elt, elt, elt, elt]).float(), model, loss=cost)[2]
    #     # x3.append(res)
    #     # x3.append(get_sensitivities.gradient_expected_val(torch.tensor([5, 2., elt, elt, elt, elt]).float(), model, loss=cost)[2])
    #     # x2.append(f(2., elt))
    #     x2.append(f(2., elt))
    # print(np.argmin(np.abs(x2)), np.argmin(np.abs(x3)))#, np.argmin(np.abs(x1)))

    # plt.scatter(np.linspace(0.1, 2, 50), x2, marker='x', label='exact')
    # # plt.scatter(np.linspace(0.1, 2, 50), x1, marker='+', label='FSP')
    # plt.scatter(np.linspace(0.1, 2., 50), x3, marker='+', label='MDN')
    # plt.legend()
    # plt.show()

    # Optimisation
    start = time.time()
    control_params, loss = optimizer.optimisation(gamma=0.005, n_iter=10_000, tolerance_rounds=20, tolerance=1e-2)
    end=time.time()
    print('time:', end-start)
    print('results', control_params, loss)
    optimizer.plot_control_values()
    optimizer.plot_losses_trajectory()
    optimizer.plot_control_params_trajectory()
    sim = generate_data.CRN_Simulations(crn, np.array([5, 10, 15, 20]), 1_000, 0, complete_trajectory=False, sampling_times=np.arange(21))
    sim.plot_simulations(np.concatenate((fixed_params, control_params)), targets=np.array([[5., 3.], [10., 2.], [15., 1.], [20., 0.]]))
    plt.show()
    
    
    