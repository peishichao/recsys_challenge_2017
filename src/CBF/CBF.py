from src.utils.loader import *
from scipy.sparse import *
import numpy as np
import numpy.linalg as la
import scipy.sparse.linalg as sLA
from sklearn.feature_extraction.text import TfidfTransformer
from src.utils.feature_weighting import *
from src.utils.matrix_utils import compute_cosine, top_k_filtering
from src.utils.BaseRecommender import BaseRecommender


class ContentBasedFiltering(BaseRecommender):

    def __init__(self, shrinkage=10, k_filtering=200):
        # final matrix of predictions
        self.R_hat = None

        # for keeping reference between playlist and row index
        self.pl_id_list = []
        # for keeping reference between tracks and column index
        self.tr_id_list = []

        self.shrinkage = shrinkage
        self.k_filtering = k_filtering

    def fit(self, urm, target_playlist, target_tracks, dataset, urm_weight=0.4):
        """
        urm: user rating matrix
        target playlist is a list of playlist id
        target_tracks is a list of track id
        shrinkage: shrinkage factor for significance weighting
        S = ICM' ICM
        R = URM S
        In between eliminate useless row of URM and useless cols of S
        """
        # initialization

        self.pl_id_list = list(target_playlist)
        self.tr_id_list = list(target_tracks)
        self.dataset = dataset
        S = None
        print("CBF started")

        # get ICM from dataset, assume it already cleaned
        icm = dataset.build_icm_2()
        icm = dataset.add_tracks_num_rating_to_icm(icm, urm)
        icm = dataset.add_playlist_to_icm(icm, urm, urm_weight)
        S = compute_cosine(icm.transpose()[[dataset.get_track_index_from_id(x)
                                            for x in self.tr_id_list]],
                           icm,
                           k_filtering=self.k_filtering,
                           shrinkage=self.shrinkage)
        s_norm = S.sum(axis=1)

        # normalize s
        S = S.multiply(csr_matrix(np.reciprocal(s_norm)))

        # compute ratings
        print("Similarity matrix ready!")
        urm_cleaned = urm[[dataset.get_playlist_index_from_id(x)
                           for x in self.pl_id_list]]
        self.S = S.transpose()

        # compute ratings
        R_hat = urm_cleaned.dot(S.transpose().tocsc()).tocsr()
        print("R_hat done")
        urm_cleaned = urm_cleaned[:, [dataset.get_track_index_from_id(x)
                                      for x in self.tr_id_list]]
        R_hat[urm_cleaned.nonzero()] = 0
        R_hat.eliminate_zeros()
        self.R_hat = R_hat

    def getW(self):
        """
        Returns the similary matrix with dimensions I x I
        S is IxT
        """
        return self.S.tocsr()

    def predict(self, at=5):
        """
        returns a dictionary of
        'pl_id': ['tr_1', 'tr_at'] for each playlist in target playlist
        """
        recs = {}
        for i in range(0, self.R_hat.shape[0]):
            pl_id = self.pl_id_list[i]
            pl_row = self.R_hat.data[self.R_hat.indptr[i]:
                                     self.R_hat.indptr[i + 1]]
            # get top 5 indeces. argsort, flip and get first at-1 items
            sorted_row_idx = np.flip(pl_row.argsort(), axis=0)[0:at]
            track_cols = [self.R_hat.indices[self.R_hat.indptr[i] + x]
                          for x in sorted_row_idx]
            tracks_ids = [self.tr_id_list[x] for x in track_cols]
            recs[pl_id] = tracks_ids
        return recs

    def getR_hat(self):
        return self.R_hat


    def get_model(self):
        """
        Returns the complete R_hat
        """
        return self.R_hat.copy()
