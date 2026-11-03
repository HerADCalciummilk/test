"""
ALGLIB 数值接口的 numpy/scipy 替代。

提供 ``randomreal``、``pearsoncorr2``、稀疏 LSQR（光流窗口求解）。
"""
import random
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import lsqr


class _math:
    @staticmethod
    def randomreal():
        return random.random()


class _lsqr_report:
    def __init__(self):
        self.terminationtype = 0


def pearsoncorr2(x, y):
    """Pearson correlation between two 1D arrays."""
    x_arr = np.array(x)
    y_arr = np.array(y)
    r = np.corrcoef(x_arr, y_arr)[0, 1]
    if np.isnan(r):
        return 0.0
    return r


def sparsecreate(n, m):
    """Create a sparse matrix builder with n rows and m columns."""
    return {'rows': [], 'cols': [], 'data': [], 'n': n, 'm': m}


def sparseset(s, i, j, v):
    """Set a value in the sparse matrix builder."""
    s['rows'].append(i)
    s['cols'].append(j)
    s['data'].append(v)


def sparseconverttocrs(s):
    """Convert the builder to a scipy CSR matrix."""
    s['matrix'] = csr_matrix((s['data'], (s['rows'], s['cols'])),
                              shape=(s['n'], s['m']))


def linlsqrcreate(n, m):
    """Create an LSQR solver state."""
    return {'n': n, 'm': m, 'damp': 0.0}


def linlsqrsetlambdai(state, lambdai):
    """Set damping parameter."""
    state['damp'] = lambdai


def linlsqrsolvesparse(state, s, b):
    """Solve sparse linear least squares using LSQR."""
    A = s['matrix']
    b_arr = np.array(b)
    damp = state.get('damp', 0.0)
    result = lsqr(A, b_arr, damp=damp, atol=1e-09, btol=1e-09, show=False)
    state['x'] = result[0]
    state['istop'] = result[1]
    state['itn'] = result[2]
    # terminationtype 4 means converged
    state['rep'] = _lsqr_report()
    state['rep'].terminationtype = 4 if state['istop'] in [1, 2, 3, 4] else 1


def linlsqrresults(state):
    """Get results from LSQR solve."""
    return state['x'], state['rep']
