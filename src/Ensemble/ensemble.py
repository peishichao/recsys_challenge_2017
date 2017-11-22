from src.utils.loader import *
from src.utils.evaluator import *
from scipy.sparse import *
import numpy as np
import numpy.linalg as LA
import scipy.sparse.linalg as sLA
from src.utils.matrix_utils import compute_cosine, top_k_filtering
from src.utils.cluster import build_user_cluster



class Ensemble(object):

    def __init__(self, models, normalize_ratings=False):
        """
        models is a list of recommender models implementing fit
        each model should implement BaseRecommender class
        """
        self.dataset = None
        self.models = models
        self.normalize_ratings = normalize_ratings

    def mix(self, params):
        """
        takes an array of models all with R_hat as atttribute
        and mixes them using params
        params: array of attributes
        """
        R_hat_mixed = lil_matrix(
            (models[0].R_hat.shape[0], models[0].R_hat.shape[1]))
        for i in range(len(self.models)):
            if self.normalize_ratings:
                current_r_hat = self.max_normalize(self.models[i].R_hat)
            else:
                current_r_hat = self.models[i].R_hat
            R_hat_mixed += current_r_hat.multiply(params[i])
        return R_hat_mixed.tocsr()

    def mix_cluster(self, models, params, tg_playlist, urm=None, icm=None, ds=None):

        urm_red = urm[[ds.get_playlist_index_from_id(x) for x in tg_playlist]]
        ucm = ds.build_ucm()[:, [ds.get_playlist_index_from_id(x)
                                 for x in tg_playlist]]

        # user cluster contains only cluster of target users
        user_cluster = build_user_cluster(
            urm_red, icm, ucm, int(len(params)))  # / 3))

        R_hat_mixed = lil_matrix(
            (models[0].R_hat.shape[0], models[0].R_hat.shape[1]))
        for i in range(len(models)):
            # normalize weights to 0,1 if needed
            if normalize_ratings:
                current_r_hat = max_normalize(models[i].R_hat)
            else:
                current_r_hat = models[i].R_hat

            # build a column vector of weights for each user
            weights = [params[user_cluster(x) + i * len(user_cluster)]
                       for x in range(len(user_cluster))]
            # weights as column vector
            np_weights = np.reshape(np.array(weights), (-1, 1))

            # multiply weights by the current matrix
            R_hat_mixed += current_r_hat.multiply(np_weights)

        return R_hat_mixed.tocsr()

    def max_normalize(self, X):
        """
        Normalizes X by rows dividing each row by its max
        """
        max_r = X.max(axis=1)
        max_r.data = np.reciprocal(max_r.data)
        return X.multiply(max_r)

    def predict(self, params, at=5):
        # Mix them all
        R_hat = self.mix(params)
        """
        returns a dictionary of
        'pl_id': ['tr_1', 'tr_at'] for each playlist in target playlist
        """
        recs = {}
        for i in range(0, R_hat.shape[0]):
            pl_id = self.pl_id_list[i]
            pl_row = R_hat.data[R_hat.indptr[i]:
                                R_hat.indptr[i + 1]]
            # get top 5 indeces. argsort, flip and get first at-1 items
            sorted_row_idx = np.flip(pl_row.argsort(), axis=0)[0:at]
            track_cols = [R_hat.indices[R_hat.indptr[i] + x]
                          for x in sorted_row_idx]
            tracks_ids = [self.tr_id_list[x] for x in track_cols]
            recs[pl_id] = tracks_ids
        return recs

    def fit(self, urm, tg_tracks, tg_playlist, ds):
        """
        Fit all models
        """
        self.tr_id_list = tg_tracks
        self.pl_id_list = tg_playlist

        # call fit on all models
        for model in self.models:
            model.fit(urm.copy(), tg_playlist, tg_tracks, ds)

    def fit_cluster(self, params):
        ds = Dataset(load_tags=True, filter_tag=True)
        ds.set_track_attr_weights(1, 0.9, 0.2, 0.2, 0.2)
        ds.set_playlist_attr_weights(1, 1, 1, 1, 1)
        ev = Evaluator()
        ev.cross_validation(5, ds.train_final.copy())
        xbf = xSquared()
        urm, tg_tracks, tg_playlist = ev.get_fold(ds)
        xbf.fit(urm.copy(), tg_playlist, tg_tracks, ds)
        recs_xbf = xbf.predict()
        # Mix them all
        models = [xbf]  # cbf, ubf]
        R_hat_mixed = mix(models, params, normalize_ratings=False)
        recs_mix = predict(R_hat_mixed, list(tg_playlist), list(tg_tracks))
        map_5 = ev.evaluate_fold(recs_mix)

        # multiply both
        R_hat_mult = max_normalize(xbf.R_hat).multiply(
            max_normalize(cbf.R_hat)).multiply(max_normalize(ubf.R_hat))
        recs_mult = predict(R_hat_mult, list(tg_playlist), list(tg_tracks))
        ev.evaluate_fold(recs_mult)

        print("MAP@5 :", map_5)
        return -map_5


def main():
    # Best params:
    # XBF: 0.0033407193133514488
    # CBF: 0.38028525074128705
    # UBF: 0.00962408557454575
    # IALS: 0.06898631305777138
    ds = Dataset(load_tags=True, filter_tag=True)
    ds.set_track_attr_weights(1, 1, 0.2, 0.2, 0.2)
    ds.set_playlist_attr_weights(0.5, 0.5, 0.5, 0.05, 0.05)
    ev = Evaluator()
    params = [0.00334, 0.3802, 0.0096, 0.0689]
    ev.cross_validation(4, ds.train_final.copy())
    for i in range(0, 4):
        ensemble = Ensemble()
        urm, tg_tracks, tg_playlist = ev.get_fold(ds)
        test_dict = ev.get_test_dict(i)
        ensemble.fit(urm, list(tg_tracks),
                list(tg_playlist),
                ds)
        recs = ensemble.predict(params)
        ev.evaluate_fold(recs)
    map_at_five = ev.get_mean_map()
    print("MAP@5 ", map_at_five)

    # export csv
    ensemble = Ensemble()
    urm = ds.build_train_matrix()
    tg_playlist = list(ds.target_playlists.keys())
    tg_tracks = list(ds.target_tracks.keys())
    # Train the model with the best shrinkage found in cross-validation
    ensemble.fit(urm,
                     tg_tracks,
                     tg_playlist,
                     ds)
    recs = ensemble.predict(params)
    with open('submission_cbf.csv', mode='w', newline='') as out:
        fieldnames = ['playlist_id', 'track_ids']
        writer = csv.DictWriter(out, fieldnames=fieldnames, delimiter=',')
        writer.writeheader()
        for k in tg_playlist:
            track_ids = ''
            for r in recs[k]:
                track_ids = track_ids + r + ' '
            writer.writerow({'playlist_id': k,
                             'track_ids': track_ids[:-1]})

if __name__ == '__main__':
    print("Ensemble started")
    main()
