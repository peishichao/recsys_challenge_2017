from loader_v2 import *
from scipy.sparse import *
import evaluator
from item_based_filtering import *


def main():
    best_map = 0
    best_shrinkage = 0
    best_k_filtering = 0
    for shr in range(30, 100, 10):
        for k_f in range(20, 100, 5):
            ds = Dataset()
            ev = evaluator.Evaluator()
            ev.cross_validation(5, ds.train_final.copy())
            ibf = ItemBasedFiltering()
            for i in range(0, 5):
                urm, tg_tracks, tg_playlist = ev.get_fold(ds)
                ibf.fit(urm, tg_playlist, tg_tracks, ds, shr, k_f)
                recs = ibf.predict()
                ev.evaluate_fold(recs)
            map_at_five = ev.get_mean_map()
            print("MAP@5 [Shrinkage = " + str(shr) +  ' K_f ' + str(k_f) + ']', map_at_five)
            # Store best shrinkage factor according to highest MAP
            if map_at_five > best_map:
                best_map = map_at_five
                best_shrinkage = shr
                best_k_filtering = k_f
    print(('Best MAP@5 = ' + str(best_map) +
           ' [Shrinkage factor:' + str(best_shrinkage) +
           ', K_f ' + str(best_k_filtering) + ']'))
    # export csv
    ibf_exporter = ItemBasedFiltering()
    urm = ds.build_train_matrix()
    tg_playlist = list(ds.target_playlists.keys())
    tg_tracks = list(ds.target_tracks.keys())
    # Train the model with the best shrinkage found in cross-validation
    ibf_exporter.fit(urm,
                     tg_playlist,
                     tg_tracks,
                     ds,
                     best_shrinkage,
                     best_k_filtering)
    recs = ibf_exporter.predict()
    with open('submission_ibf.csv', mode='w', newline='') as out:
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
    main()
