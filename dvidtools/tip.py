# This code is part of dvid-tools (https://github.com/flyconnectome/dvid_tools)
# and is released under GNU GPL3

from . import utils
from . import fetch

import datetime as dt
import numpy as np
import pandas as pd

from scipy.spatial.distance import cdist
from tqdm import tqdm


def detect_tips(x, psd_dist=10, done_dist=50, checked_dist=50,
                pos_filter=None, save_to=None, verbose=True,
                server=None, node=None):
    """ Detects potential open ends on a given neuron.

    In brief, this script gets the skeleton's leaf nodes and checks if they
    are in proximity to a postsynaptic density (PSD). If not, the tip is
    flagged a potential open end.

    Parameters
    ----------
    x :             single body ID
    psd_dist :      int | None, optional
                    Minimum distance (in raw units) to a PSD for a tip to be
                    considered "done".
    done_dist :     int | None,
                    Minimum distance (in raw units) to a DONE tag for a tip
                    to be considered "done".
    checked_dist :  int | None, optional
                    Minimum distance (in raw units) to a bookmark that has
                    previously been "Set Checked" in the "Assigned bookmarks"
                    table in Neutu.
    pos_filter :    function, optional
                    Function to tips by position. Must accept
                    numpy array (N, 3) and return array of [True, False, ...]
    save_to :       filepath, optional
                    If provided will save open ends to JSON file that can be
                    imported as assigmnents.
    server :        str, optional
                    If not provided, will try reading from global.
    node :          str, optional
                    If not provided, will try reading from global.

    Return
    ------
    pandas.DataFrame
                    Open ends. Only if ``save_to=None``.
    """

    # Get the skeleton
    n = fetch.get_skeleton(x, save_to=None, server=server, node=node)

    # Turn into DataFrame
    n, header = utils.parse_swc_str(n)

    # Find leaf nodes
    leafs = n[~n.node_id.isin(n.parent_id.values)]

    if pos_filter:
        # Get filter
        filtered = pos_filter(leafs[['x','y','z']].values)

        if not any(filtered):
            raise ValueError('No tips left after filtering!')

        leafs = leafs.loc[filtered, :]

    n_leafs = leafs.shape[0]

    if psd_dist:
        # Get synapses
        syn = fetch.get_synapses(x, pos_filter=None, with_details=False,
                                 server=server, node=node)
        post = syn[syn.Kind=='PostSyn']

        # Get distances
        dist = cdist(leafs[['x', 'y', 'z']].values,
                     np.vstack(post.Pos.values))

        # Is tip close to PSD?
        at_psd = np.min(dist, axis=1) < psd_dist

        leafs = leafs[~at_psd]

    psd_filtered = n_leafs - leafs.shape[0]

    if done_dist:
        # Check for DONE tags in vicinity
        at_done = []
        for pos in tqdm(leafs[['x', 'y', 'z']].values,
                        desc='Check DONE', leave=False):
            # We are cheating here b/c we don't actually calculate the
            # distance!
            labels = fetch.get_labels_in_area(pos - done_dist/2,
                                              [done_dist] * 3,
                                              server=server, node=node)

            if isinstance(labels, type(None)):
                at_done.append(False)
                continue

            # DONE tags have no "action" and "checked" = 1
            if any([p.get('checked', False) and not p.get('action', False) for p in labels.Prop.values]):
                at_done.append(True)
            else:
                at_done.append(False)

        leafs = leafs[~np.array(at_done, dtype=bool)]

    done_filtered = n_leafs - leafs.shape[0]

    if checked_dist:
        # Check if position has been "Set Checked" in the past
        checked = []
        for pos in tqdm(leafs[['x', 'y', 'z']].values,
                        desc='Test Checked', leave=False):
            # We will look for the assigment in a small window in case the
            # tip has moved slightly between iterations
            ass = fetch.get_assignment_status(pos, window=[checked_dist]*3,
                                              server=server, node=node)

            if any([l.get('checked', False) for l in ass]):
                checked.append(True)
            else:
                checked.append(False)

        leafs = leafs[~np.array(checked, dtype=bool)]

    checked_filtered = n_leafs - leafs.shape[0]

    # Make a copy before we wrap up to prevent any data-on-copy warning
    leafs = leafs.copy()

    # Assuming larger radii indicate more likely continuations
    leafs.sort_values('radius', ascending=False, inplace=True)

    if verbose:
        d = {'open ends': leafs.shape[0],
             'total ends': n_leafs,
             'at PSD': psd_filtered,
             'at Done tag': done_filtered,
             'at checked assignment': checked_filtered,
            }
        print(pd.DataFrame.from_dict(d, orient='index', columns=[x]))

    if save_to:
        leafs['body ID'] = x
        leafs['text'] = ''
        meta = {'description': 'Generated by dvidtools.detect_tips',
                'date': dt.date.today().isoformat(),
                'url': 'https://github.com/flyconnectome/dvid_tools',
                'parameters' : {'psd_dist': psd_dist,
                                'done_dost': done_dist,
                                'checked_dist': checked_dist}}
        _ = utils.gen_assignments(leafs, save_to=save_to, meta=meta)
    else:
        return leafs.reset_index(drop=True)




