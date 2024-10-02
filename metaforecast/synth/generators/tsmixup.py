import numpy as np
import pandas as pd

from metaforecast.synth.generators._base import SemiSyntheticGenerator


class TSMixup(SemiSyntheticGenerator):

    def __init__(self,
                 max_n_uids: int,
                 min_len: int,
                 max_len: int,
                 dirichlet_alpha: float = 1.5):
        super().__init__(alias='TSMixup')

        self.min_len = min_len
        self.max_len = max_len
        self.max_n_uids = max_n_uids
        self.dirichlet_alpha = dirichlet_alpha

    def transform(self, df: pd.DataFrame, n_series: int = -1):
        unq_uids = df['unique_id'].unique()

        if n_series < 0:
            n_series = len(unq_uids)

        dataset = []
        for i in range(n_series):
            n_uids = np.random.randint(1, self.max_n_uids + 1)

            selected_uids = np.random.choice(unq_uids, n_uids, replace=False).tolist()

            df_uids = df.query('unique_id == @selected_uids')

            ts_df = self._create_synthetic_ts(df_uids)
            ts_df['unique_id'] = f'{self.alias}_{self.counter}'
            self.counter += 1

            dataset.append(ts_df)

        synth_df = pd.concat(dataset).reset_index(drop=True)

        return synth_df

    def _create_synthetic_ts(self, df: pd.DataFrame) -> pd.DataFrame:
        uids = df['unique_id'].unique()

        smallest_n = df['unique_id'].value_counts().min()

        if smallest_n < self.max_len:
            max_len_ = smallest_n
        else:
            max_len_ = self.max_len

        if self.min_len == self.max_len:
            n_obs = self.min_len
        else:
            n_obs = np.random.randint(self.min_len, max_len_ + 1)

        w = self.sample_weights_dirichlet(self.dirichlet_alpha, len(uids))

        ds = df.query(f'unique_id=="{uids[0]}"').head(n_obs)['ds'].values

        mixup = []
        for j, k in enumerate(uids):
            uid_df = df.query(f'unique_id=="{k}"').head(n_obs)

            uid_y = uid_df['y'].reset_index(drop=True)
            uid_y /= uid_y.mean()
            uid_y *= w[j]

            mixup.append(uid_y)

        y = pd.concat(mixup, axis=1).sum(axis=1).values

        synth_df = pd.DataFrame({'ds': ds, 'y': y, })

        return synth_df
