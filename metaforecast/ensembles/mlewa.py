import typing

import pandas as pd
import numpy as np

from metaforecast.ensembles.base import Mixture

RowIDType = typing.Union[int, typing.Hashable]


class MLewa(Mixture):
    """ MLewa

    Dynamic expert aggregation based on exponentially-weighted average based on R's opera package

    References:
        Cesa-Bianchi, Nicolo, and Gábor Lugosi. Prediction, learning, and games. Cambridge university press, 2006.

        Gaillard, P., & Goude, Y. (2015). Forecasting electricity consumption by aggregating experts;
        how to design a good set of experts. In Modeling and stochastic learning for forecasting in high dimensions
        (pp. 95-115). Cham: Springer International Publishing.

        Cerqueira, V., Torgo, L., Pinto, F., & Soares, C. (2019). Arbitrage of forecasting experts.
        Machine Learning, 108, 913-944.

    Basic example usage (CHECK NOTEBOOKS FOR MORE SERIOUS EXAMPLES):
    >>> from datasetsforecast.m3 import M3
    >>> from neuralforecast import NeuralForecast
    >>> from neuralforecast.models import NHITS, NBEATS, MLP
    >>> from metaforecast.ensembles import MLewa
    >>>
    >>> df, *_ = M3.load('.', group='Monthly')
    >>>
    >>> CONFIG = {'input_size': 12,
    >>>           'h': 12,
    >>>           'accelerator': 'cpu',
    >>>           'max_steps': 10, }
    >>>
    >>> models = [
    >>>     NBEATS(**CONFIG, stack_types=3 * ["identity"]),
    >>>     NHITS(**CONFIG),
    >>>     MLP(**CONFIG),
    >>>     MLP(num_layers=3, **CONFIG),
    >>> ]
    >>>
    >>> nf = NeuralForecast(models=models, freq='M')
    >>>
    >>> # cv to build meta-data
    >>> n_windows = df['unique_id'].value_counts().min()
    >>> n_windows = int(n_windows // 2)
    >>> fcst_cv = nf.cross_validation(df=df, n_windows=n_windows, step_size=1)
    >>> fcst_cv = fcst_cv.reset_index()
    >>> fcst_cv = fcst_cv.groupby(['unique_id', 'cutoff']).head(1).drop(columns='cutoff')
    >>>
    >>> # fitting combination rule
    >>> ensemble = MLewa(loss_type='square', gradient=True, trim_ratio=.8)
    >>> ensemble.fit(fcst_cv)
    >>>
    >>> # re-fitting models
    >>> nf.fit(df=df)
    >>>
    >>> # forecasting and combining
    >>> fcst = nf.predict()
    >>> fcst_ensemble = ensemble.predict(fcst.reset_index())
    """

    def __init__(self,
                 loss_type: str,
                 gradient: bool,
                 weight_by_uid: bool = False,
                 trim_ratio: float = 1):

        """
        :param loss_type: Loss function used to quantify forecast accuracy of ensemble members.
        Should be one of 'square', 'pinball', 'percentage', 'absolute', or 'log'
        :type loss_type: str

        :param gradient: Whether to use the gradient trick to weight ensemble members
        :type gradient: bool

        :param weight_by_uid: Whether to weight the ensemble by unique_id (True) or dataset (False)
        Defaults to True, but this can become computationally demanding for datasets with a large number of time series
        :type weight_by_uid: bool

        :param trim_ratio: Ratio (0-1) of ensemble members to keep in the ensemble.
        (1-trim_ratio) of models will not be used during inference based on validation accuracy.
        Defaults to 1, which means all ensemble members are used.
        :type trim_ratio: float
        """

        super().__init__(loss_type=loss_type,
                         gradient=gradient,
                         trim_ratio=trim_ratio,
                         weight_by_uid=weight_by_uid)

        self.alias = 'MLewa'

    def _update_mixture(self, fcst: pd.DataFrame, y: np.ndarray, **kwargs):
        """ _update_mixture

        Updating the weights of the ensemble

        :param fcst: predictions of the ensemble members (columns) in different time steps (rows)
        :type fcst: pd.DataFrame

        :param y: actual values of the time series
        :type y: np.ndarray

        :return: self
        """

        for i, fc in fcst.iterrows():
            w = self._weights_from_regret(iteration=i)

            self.weights[i], self.ensemble_fcst[i] = self._calc_ensemble_fcst(fc, w)

            loss_experts = self._calc_loss(fcst=fc, y=y[i], fcst_c=self.ensemble_fcst[i])
            loss_mixture = self._calc_loss(fcst=self.ensemble_fcst[i], y=y[i], fcst_c=self.ensemble_fcst[i])

            regret_i = (loss_mixture - loss_experts)

            # update regret
            for mod in self.regret:
                self.regret[mod] += regret_i[mod]

            n = len(self.model_names)
            self.eta[int(str(i)) + 1] = np.sqrt(np.log(n) / (np.log(n) / self.eta[i] ** 2 + regret_i ** 2))

    def _weights_from_regret(self, iteration: RowIDType = -1):
        """ _weights_from_regret

        Updating the weights based on regret minimization

        """
        curr_regret = np.array(list(self.regret.values()))

        if np.max(curr_regret) > 0:
            w = self.truncate_loss(np.exp(self.eta[iteration] * curr_regret))
            w /= np.sum(w)
        else:
            w = np.ones_like(curr_regret) / len(curr_regret)

        w = pd.Series(w, index=self.model_names)

        return w

    def _initialize_params(self, fcst: pd.DataFrame):

        n_row, n_col = fcst.shape[0], len(self.model_names)

        self.eta = np.full(shape=(n_row + 1, n_col), fill_value=np.exp(350))
        self.regret = {k: 0 for k in self.model_names}
        self.weights = np.zeros((n_row, n_col))
        self.ensemble_fcst = np.zeros(n_row)

    def update_weights(self, fcst: pd.DataFrame):
        raise NotImplementedError

    @staticmethod
    def truncate_loss(x):
        return np.clip(x, np.exp(-700), np.exp(700))
