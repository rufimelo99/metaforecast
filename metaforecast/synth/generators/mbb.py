import numpy as np
import pandas as pd
import torch
from statsmodels.tsa.api import STL
from arch.bootstrap import MovingBlockBootstrap

from metaforecast.synth.generators._base import SemiSyntheticTransformer
from metaforecast.utils.log import LogTransformation


class _SeasonalMBB:

    @staticmethod
    def _get_mbb(x: pd.Series, w: int, n_samples: int = 1):
        mbb = MovingBlockBootstrap(block_size=w, x=x)

        xt = mbb.bootstrap(n_samples)
        xt = list(xt)
        mbb_series = xt[0][1]['x']

        return mbb_series

    @classmethod
    def create_bootstrap(cls, y: np.ndarray, seas_period: int, log: bool) -> np.ndarray:

        if log:
            y = LogTransformation.transform(y)

        try:
            stl = STL(y, period=seas_period).fit()

            try:
                synth_res = cls._get_mbb(stl.resid, seas_period)
            except ValueError:
                synth_res = pd.Series(stl.resid).sample(len(stl.resid), replace=True).values

            synth_ts = stl.trend + stl.seasonal + synth_res
        except ValueError:
            synth_ts = y

        if log:
            synth_ts = LogTransformation.inverse_transform(synth_ts)

        return synth_ts


class SeasonalMBB(SemiSyntheticTransformer):

    def __init__(self, seas_period: int, log: bool = True):
        super().__init__(alias='MBB')

        self.log = log
        self.seas_period = seas_period

    def _create_synthetic_ts(self, df: pd.DataFrame) -> pd.DataFrame:
        ts = df['y'].copy().values

        synth_ts = _SeasonalMBB.create_bootstrap(ts, seas_period=self.seas_period, log=self.log)

        df['y'] = synth_ts

        return df

#
# class SeasonalMBBTensor(TSDataGeneratorTensor):
#
#     def __init__(self,
#                  seas_period: int,
#                  log: bool = True,
#                  augment: bool = True):
#         super().__init__(augment=augment)
#
#         self.log = log
#         self.seas_period = seas_period
#
#         self.fit()
#
#     def fit(self, **kwargs) -> 'SeasonalMBBTensor':
#         pass
#
#     def _create_synthetic_ts(self, y: np.ndarray) -> torch.tensor:
#         return _SeasonalMBB.create_bootstrap(y, seas_period=self.seas_period, log=self.log)
