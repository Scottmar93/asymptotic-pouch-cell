#
# Compare "full" 2D (COMSOL) to recued 1+1D DFN and DFNCC
# Here "bar" refers to the averaged through-cell model (i.e. DFNCC)
#

import pybamm
import sys
import pickle
import matplotlib
import matplotlib.pyplot as plt
import shared
import numpy as np

# set style
matplotlib.rc_file("_matplotlibrc", use_default_template=True)

# increase recursion limit for large expression trees
sys.setrecursionlimit(100000)

pybamm.set_logging_level("INFO")


"-----------------------------------------------------------------------------"
"Load comsol data"

comsol_variables = pickle.load(open("comsol_data/comsol_1plus1D_3C.pickle", "rb"))

"-----------------------------------------------------------------------------"
"Set up and solve pybamm simulation"

# load current collector and DFN models
cc_model = pybamm.current_collector.EffectiveResistance1D()
dfn_av = pybamm.lithium_ion.DFN({"thermal": "x-lumped"}, name="Average DFN")
dfn = pybamm.lithium_ion.DFN(
    {"current collector": "potential pair", "dimensionality": 1, "thermal": "x-lumped"},
    name="1+1D DFN",
)
models = {"Current collector": cc_model, "Average DFN": dfn_av, "1+1D DFN": dfn}

# parameters
param = dfn.default_parameter_values
param.update({"C-rate": 3})


# process model and geometry, and discretise
meshes = {}
for name, model in models.items():
    param.process_model(model)
    geometry = model.default_geometry
    param.process_geometry(geometry)

    # set mesh
    var = pybamm.standard_spatial_vars
    submesh_types = model.default_submesh_types
    # set npts
    var = pybamm.standard_spatial_vars
    npts = 16
    var_pts = {
        var.x_n: npts,
        var.x_s: npts,
        var.x_p: npts,
        var.r_n: npts,
        var.r_p: npts,
        var.z: npts,
    }
    meshes[name] = pybamm.Mesh(geometry, submesh_types, var_pts)
    disc = pybamm.Discretisation(meshes[name], model.default_spatial_methods)
    disc.process_model(model, check_model=False)

# discharge timescale
tau = param.evaluate(pybamm.standard_parameters_lithium_ion.tau_discharge)

# solve model at comsol times
t_eval = comsol_variables["time"] / tau

solutions = {}
for name, model in models.items():
    if name == "Current collector":
        solver = pybamm.AlgebraicSolver(tol=1e-6)
        solutions[name] = solver.solve(model)
    else:
        # solver
        solver = pybamm.CasadiSolver(
            atol=1e-6, rtol=1e-6, root_tol=1e-3, root_method="hybr", mode="fast"
        )
        solutions[name] = solver.solve(model, t_eval)


"-----------------------------------------------------------------------------"
"Make Comsol 'model' for comparison"

mesh = meshes["1+1D DFN"]
comsol_model = shared.make_comsol_model(comsol_variables, mesh, param, thermal=True)


"-----------------------------------------------------------------------------"
"Make plots"
t_plot = comsol_model.t
z_plot = comsol_model.z_interp
t_slices = np.array([600, 1200, 1800, 2400, 3000]) / 3

# get processed potentials from DFNCC
R_cc = param.process_symbol(
    cc_model.variables["Effective current collector resistance"]
).evaluate(t=solutions["Current collector"].t, y=solutions["Current collector"].y)[0][0]

V_av_1D = pybamm.ProcessedVariable(
    dfn_av.variables["Terminal voltage"],
    solutions["Average DFN"].t,
    solutions["Average DFN"].y,
    mesh=meshes["Average DFN"],
)
I_av = pybamm.ProcessedVariable(
    dfn_av.variables["Total current density"],
    solutions["Average DFN"].t,
    solutions["Average DFN"].y,
    mesh=meshes["Average DFN"],
)


def V_av(t):
    return V_av_1D(t) - I_av(t) * R_cc


potentials = cc_model.get_processed_potentials(
    solutions["Current collector"], meshes["Current collector"], param, V_av, I_av
)

# plot negative current collector potential
var = "Negative current collector potential [V]"
comsol_var_fun = pybamm.ProcessedVariable(
    comsol_model.variables[var],
    solutions["1+1D DFN"].t,
    solutions["1+1D DFN"].y,
    mesh=meshes["1+1D DFN"],
)
pybamm_var_fun = pybamm.ProcessedVariable(
    models["1+1D DFN"].variables[var],
    solutions["1+1D DFN"].t,
    solutions["1+1D DFN"].y,
    mesh=meshes["1+1D DFN"],
)

pybamm_bar_var_fun = potentials[var]
shared.plot_tz_var(
    t_plot,
    z_plot,
    t_slices,
    "$\phi^*_{\mathrm{s,cn}}$",
    "[V]",
    comsol_var_fun,
    pybamm_var_fun,
    pybamm_bar_var_fun,
    param,
    cmap="cividis",
)

# plot positive current collector potential (with respect to terminal voltage)
var = "Positive current collector potential [V]"
comsol_var = pybamm.ProcessedVariable(
    comsol_model.variables[var],
    solutions["1+1D DFN"].t,
    solutions["1+1D DFN"].y,
    mesh=meshes["1+1D DFN"],
)
V_comsol = pybamm.ProcessedVariable(
    comsol_model.variables["Terminal voltage [V]"],
    solutions["1+1D DFN"].t,
    solutions["1+1D DFN"].y,
    mesh=meshes["1+1D DFN"],
)


def comsol_var_fun(t, z):
    return comsol_var(t=t, z=z) - V_comsol(t=t)


pybamm_var = pybamm.ProcessedVariable(
    models["1+1D DFN"].variables[var],
    solutions["1+1D DFN"].t,
    solutions["1+1D DFN"].y,
    mesh=meshes["1+1D DFN"],
)
V = pybamm.ProcessedVariable(
    models["1+1D DFN"].variables["Terminal voltage [V]"],
    solutions["1+1D DFN"].t,
    solutions["1+1D DFN"].y,
    mesh=meshes["1+1D DFN"],
)


def pybamm_var_fun(t, z):
    return pybamm_var(t=t, z=z) - V(t=t)


pybamm_bar_var = potentials[var]

pot_scale = param.evaluate(pybamm.standard_parameters_lithium_ion.potential_scale)
U_ref = param.evaluate(pybamm.standard_parameters_lithium_ion.U_p_ref) - param.evaluate(
    pybamm.standard_parameters_lithium_ion.U_n_ref
)


def V_av_dim(t):
    return U_ref + V_av(t) * pot_scale


def pybamm_bar_var_fun(t, z):
    return pybamm_bar_var(t=t, z=z) - V_av_dim(t)


shared.plot_tz_var(
    t_plot,
    z_plot,
    t_slices,
    "$\phi^*_{\mathrm{s,cp}} - V^*$",
    "[V]",
    comsol_var_fun,
    pybamm_var_fun,
    pybamm_bar_var_fun,
    param,
    cmap="viridis",
)

# plot through-cell current
var = "Current collector current density [A.m-2]"
comsol_var_fun = pybamm.ProcessedVariable(
    comsol_model.variables[var],
    solutions["1+1D DFN"].t,
    solutions["1+1D DFN"].y,
    mesh=meshes["1+1D DFN"],
)
pybamm_var_fun = pybamm.ProcessedVariable(
    models["1+1D DFN"].variables[var],
    solutions["1+1D DFN"].t,
    solutions["1+1D DFN"].y,
    mesh=meshes["1+1D DFN"],
)

I_av = pybamm.ProcessedVariable(
    dfn_av.variables["Current collector current density [A.m-2]"],
    solutions["Average DFN"].t,
    solutions["Average DFN"].y,
    mesh=meshes["Average DFN"],
)


def pybamm_bar_var_fun(t, z):
    if t.shape[0] == 1:
        return np.repeat(I_av(t)[:, np.newaxis], len(z), axis=0)
    else:
        return np.transpose(np.repeat(I_av(t)[:, np.newaxis], len(z), axis=1))


shared.plot_tz_var(
    t_plot,
    z_plot,
    t_slices,
    "$\mathcal{I}^*$",
    "[A/m${}^2$]",
    comsol_var_fun,
    pybamm_var_fun,
    pybamm_bar_var_fun,
    param,
    cmap="plasma",
)

# plot temperature
T_ref = param.evaluate(pybamm.standard_parameters_lithium_ion.T_ref)
var = "X-averaged cell temperature [K]"
comsol_var = pybamm.ProcessedVariable(
    comsol_model.variables[var],
    solutions["1+1D DFN"].t,
    solutions["1+1D DFN"].y,
    mesh=meshes["1+1D DFN"],
)


def comsol_var_fun(t, z):
    return comsol_var(t=t, z=z) - T_ref


pybamm_var = pybamm.ProcessedVariable(
    models["1+1D DFN"].variables[var],
    solutions["1+1D DFN"].t,
    solutions["1+1D DFN"].y,
    mesh=meshes["1+1D DFN"],
)


def pybamm_var_fun(t, z):
    return pybamm_var(t=t, z=z) - T_ref


T_av = pybamm.ProcessedVariable(
    dfn_av.variables["X-averaged cell temperature [K]"],
    solutions["Average DFN"].t,
    solutions["Average DFN"].y,
    mesh=meshes["Average DFN"],
)


def pybamm_bar_var_fun(t, z):
    if t.shape[0] == 1:
        return np.repeat(T_av(t)[:, np.newaxis], len(z), axis=0) - T_ref
    else:
        return np.transpose(np.repeat(T_av(t)[:, np.newaxis], len(z), axis=1)) - T_ref


shared.plot_tz_var(
    t_plot,
    z_plot,
    t_slices,
    "$\\bar{T}^* - \\bar{T}_0^*$",
    "[K]",
    comsol_var_fun,
    pybamm_var_fun,
    pybamm_bar_var_fun,
    param,
    cmap="inferno",
)

plt.show()
