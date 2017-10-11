from loader_v2 import *
from scipy.sparse import *
import numpy as np


class ContentBasedFiltering(object):

    def __init__(self):
        # final matrix of predictions
        self.R_hat = None

        # for keeping reference between playlist and row index
        self.pl_id_list = []
        # for keeping reference between tracks and column index
        self.tr_id_list = []

    def fit(self, urm, target_playlist, target_tracks, dataset, shrinkage=130, k_filtering=95):
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
        S = lil_matrix((len(target_tracks), dataset.tracks_number))
        print("target playlist ", len(self.pl_id_list))
        print("target tracks ", len(self.tr_id_list))
        # get ICM from dataset, assume it already cleaned
        icm = dataset.build_icm()
        # calculate similarity between items:
        # S_ij=(sum for k belonging to attributes t_ik*t_jk)/norm_i * norm_k
        # first calculate norm
        # sum over rows (obtaining a row vector)
        norm = np.sqrt(icm.sum(axis=0))
        norm[(norm == 0)] = 1
        # normalize
        icm = icm.multiply(csr_matrix(1 / norm))
        icm_t = icm.transpose()
        # clean the transposed matrix, we do not need tracks not target
        icm_t = icm_t[[dataset.get_track_index_from_id(x)
                       for x in self.tr_id_list]]
        chunksize = 1000
        mat_len = icm_t.shape[0]
        for chunk in range(0, mat_len, chunksize):
            if chunk + chunksize > mat_len:
                end = mat_len
            else:
                end = chunk + chunksize
            print(('Building cosine similarity matrix for [' +
                   str(chunk) + ', ' + str(end) + ') ...'))
            S[chunk:end] = icm_t[chunk:end].tocsr().dot(icm)
        S = S.tocsr()
        print("Similarity matrix ready, let's normalize it!")
        # zero out diagonal
        # in the diagonal there is the sim between i and i (1)
        S.setdiag(0)
        S.eliminate_zeros()
        # keep only target rows of URM
        urm_cleaned = urm[[dataset.get_playlist_index_from_id(x)
                           for x in self.pl_id_list]]
        # apply shrinkage factor:
        # Let I_uv be the set of attributes in common of item i and j
        # Let H be the shrinkage factor
        #   Multiply element-wise for the matrix of I_uv (ie: the sim matrix)
        #   Divide element-wise for the matrix of I_uv incremented by H
        # Obtaining I_uv / I_uv + H
        # Rationale:
        # if I_uv is high H has no importante, otherwise has importance
        shr_num = S
        shr_den = S.copy()
        shr_den.data += shrinkage
        shr_den = 1 / shr_den.todense()
        shr_den[(shr_den == 0)] = 1
        S = S.multiply(shr_num)
        S = csr_matrix(S.multiply(shr_den))
        # Top-K filtering.
        # We only keep the top K similarity weights to avoid considering many
        # barely-relevant neighbors
        for row_i in range(0, S.shape[0]):
            row = S.data[S.indptr[row_i]:S.indptr[row_i + 1]]

            sorted_idx = row.argsort()[:-k_filtering]
            row[sorted_idx] = 0
        S.eliminate_zeros()
        # get a column vector of the similarities of item i (i is the row)
        s_norm = S.sum(axis=1)
        # normalize s
        S = S.multiply(csr_matrix(1 / s_norm))
        # compute ratings
        R_hat = urm_cleaned.dot(S.transpose()).tocsr()
        print("R_hat done")
        # apply mask for eliminating already rated items
        R_hat[urm_cleaned.nonzero()] = 0
        R_hat.eliminate_zeros()
        # eliminate playlist that are not target, already done, to check
        #R_hat = R_hat[:, [dataset.get_track_index_from_id(
        #    x) for x in self.tr_id_list]]
        print("Shape of final matrix: ", R_hat.shape)
        self.R_hat = R_hat

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

    def get_model(self):
        """
        Returns the complete R_hat
        """
        return self.R_hat.copy()
