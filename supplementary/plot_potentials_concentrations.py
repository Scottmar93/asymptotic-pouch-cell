#
# Compare thermal models from pybamm and comsol
#

import pybamm
import numpy as np
import pickle
import scipy.interpolate as interp
import matplotlib
import matplotlib.pyplot as plt

# set style
matplotlib.rc_file("_matplotlibrc", use_default_template=True)

"-----------------------------------------------------------------------------"
"Load comsol data"

comsol_variables = pickle.load(open("comsol_data/comsol_1D_1C.pickle", "rb"))

"-----------------------------------------------------------------------------"
"Create and solve pybamm model"

# load model and geometry
pybamm.set_logging_level("INFO")
options = {"thermal": "x-full"}
pybamm_model = pybamm.lithium_ion.DFN(options)
geometry = pybamm_model.default_geometry

# load parameters and process model and geometry
param = pybamm_model.default_parameter_values
param.update({"C-rate": 1})
param.process_model(pybamm_model)
param.process_geometry(geometry)

# create mesh
var = pybamm.standard_spatial_vars
var_pts = {
    var.x_n: int(param.evaluate(pybamm.geometric_parameters.L_n / 1e-6)),
    var.x_s: int(param.evaluate(pybamm.geometric_parameters.L_s / 1e-6)),
    var.x_p: int(param.evaluate(pybamm.geometric_parameters.L_p / 1e-6)),
    var.r_n: int(param.evaluate(pybamm.geometric_parameters.R_n / 1e-7)),
    var.r_p: int(param.evaluate(pybamm.geometric_parameters.R_p / 1e-7)),
}
mesh = pybamm.Mesh(geometry, pybamm_model.default_submesh_types, var_pts)

# discretise model
spatial_methods = pybamm_model.default_spatial_methods
disc = pybamm.Discretisation(mesh, pybamm_model.default_spatial_methods)
disc.process_model(pybamm_model)

# discharge timescale
tau = param.evaluate(pybamm.standard_parameters_lithium_ion.tau_discharge)

# solve model at comsol times
time = comsol_variables["time"] / tau
solver = pybamm.CasadiSolver(atol=1e-6, rtol=1e-6, root_tol=1e-6, mode="fast")
solution = solver.solve(pybamm_model, time)


"-----------------------------------------------------------------------------"
"Make Comsol 'model' for comparison"

whole_cell = ["negative electrode", "separator", "positive electrode"]
comsol_t = comsol_variables["time"]
L_x = param.evaluate(pybamm.standard_parameters_lithium_ion.L_x)
interp_kind = "cubic"


def get_interp_fun(variable_name, domain, eval_on_edges=False):
    """
    Create a :class:`pybamm.Function` object using the variable, to allow plotting with
    :class:`'pybamm.QuickPlot'` (interpolate in space to match edges, and then create
    function to interpolate in time)
    """
    variable = comsol_variables[variable_name]
    if domain == ["negative electrode"]:
        comsol_x = comsol_variables["x_n"]
    elif domain == ["separator"]:
        comsol_x = comsol_variables["x_s"]
    elif domain == ["positive electrode"]:
        comsol_x = comsol_variables["x_p"]
    elif domain == whole_cell:
        comsol_x = comsol_variables["x"]
    # Make sure to use dimensional space
    if eval_on_edges:
        pybamm_x = mesh.combine_submeshes(*domain)[0].edges * L_x
    else:
        pybamm_x = mesh.combine_submeshes(*domain)[0].nodes * L_x
    variable = interp.interp1d(comsol_x, variable, axis=0, kind=interp_kind)(pybamm_x)

    def myinterp(t):
        return interp.interp1d(comsol_t, variable, kind=interp_kind)(t)[:, np.newaxis]

    # Make sure to use dimensional time
    fun = pybamm.Function(myinterp, pybamm.t * tau, name=variable_name + "_comsol")
    fun.domain = domain
    return fun


comsol_c_n_surf = get_interp_fun("c_n_surf", ["negative electrode"])
comsol_c_e = get_interp_fun("c_e", whole_cell)
comsol_c_p_surf = get_interp_fun("c_p_surf", ["positive electrode"])
comsol_phi_n = get_interp_fun("phi_n", ["negative electrode"])
comsol_phi_e = get_interp_fun("phi_e", whole_cell)
comsol_phi_p = get_interp_fun("phi_p", ["positive electrode"])
comsol_i_s_n = get_interp_fun("i_s_n", ["negative electrode"], eval_on_edges=True)
comsol_i_s_p = get_interp_fun("i_s_p", ["positive electrode"], eval_on_edges=True)
comsol_i_e_n = get_interp_fun("i_e_n", ["negative electrode"], eval_on_edges=True)
comsol_i_e_p = get_interp_fun("i_e_p", ["positive electrode"], eval_on_edges=True)
comsol_voltage = interp.interp1d(
    comsol_t, comsol_variables["voltage"], kind=interp_kind
)
comsol_temperature = get_interp_fun("temperature", whole_cell)
comsol_temperature_av = interp.interp1d(
    comsol_t, comsol_variables["average temperature"], kind=interp_kind
)
comsol_q_irrev_n = get_interp_fun("Q_irrev_n", ["negative electrode"])
comsol_q_irrev_p = get_interp_fun("Q_irrev_p", ["positive electrode"])
comsol_q_rev_n = get_interp_fun("Q_rev_n", ["negative electrode"])
comsol_q_rev_p = get_interp_fun("Q_rev_p", ["positive electrode"])
comsol_q_total_n = get_interp_fun("Q_total_n", ["negative electrode"])
comsol_q_total_s = get_interp_fun("Q_total_s", ["separator"])
comsol_q_total_p = get_interp_fun("Q_total_p", ["positive electrode"])

# Create comsol model with dictionary of Matrix variables
comsol_model = pybamm.BaseModel()
comsol_model.variables = {
    "Negative particle surface concentration [mol.m-3]": comsol_c_n_surf,
    "Electrolyte concentration [mol.m-3]": comsol_c_e,
    "Positive particle surface concentration [mol.m-3]": comsol_c_p_surf,
    "Current [A]": pybamm_model.variables["Current [A]"],
    "Negative electrode potential [V]": comsol_phi_n,
    "Electrolyte potential [V]": comsol_phi_e,
    "Positive electrode potential [V]": comsol_phi_p,
    "Negative electrode current density [A.m-2]": comsol_i_s_n,
    "Positive electrode current density [A.m-2]": comsol_i_s_p,
    "Negative electrolyte current density [A.m-2]": comsol_i_e_n,
    "Positive electrolyte current density [A.m-2]": comsol_i_e_p,
    "Terminal voltage [V]": pybamm.Function(
        comsol_voltage, pybamm.t * tau, name="voltage_comsol"
    ),
    "Cell temperature [K]": comsol_temperature,
    "Volume-averaged cell temperature [K]": pybamm.Function(
        comsol_temperature_av, pybamm.t * tau, name="temperature_comsol"
    ),
    "Negative electrode irreversible electrochemical heating [W.m-3]": comsol_q_irrev_n,
    "Positive electrode irreversible electrochemical heating [W.m-3]": comsol_q_irrev_p,
    "Negative electrode reversible heating [W.m-3]": comsol_q_rev_n,
    "Positive electrode reversible heating [W.m-3]": comsol_q_rev_p,
    "Negative electrode total heating [W.m-3]": comsol_q_total_n,
    "Separator total heating [W.m-3]": comsol_q_total_s,
    "Positive electrode total heating [W.m-3]": comsol_q_total_p,
}

"-----------------------------------------------------------------------------"
"Plot comparison"

# Get mesh nodes for spatial plots
x_n_nodes = mesh.combine_submeshes(*["negative electrode"])[0].nodes
x_s_nodes = mesh.combine_submeshes(*["separator"])[0].nodes
x_p_nodes = mesh.combine_submeshes(*["positive electrode"])[0].nodes
x_nodes = mesh.combine_submeshes(*whole_cell)[0].nodes
x_n_edges = mesh.combine_submeshes(*["negative electrode"])[0].edges
x_s_edges = mesh.combine_submeshes(*["separator"])[0].edges
x_p_edges = mesh.combine_submeshes(*["positive electrode"])[0].edges
x_edges = mesh.combine_submeshes(*whole_cell)[0].edges

# Define plotting functions


def electrode_comparison_plot(
    var, labels, plot_times=None, eval_on_edges=False, sharex=False
):
    """
    Plot pybamm variable against comsol variable (both defined separately in the
    negative and positive electrode) E.g. if var = "electrode current density [A.m-2]"
    then the variables "Negative electrode current density [A.m-2]" and "Positive
    electrode current density [A.m-2]" will be plotted.

    Parameters
    ----------

    var : str
        The name of the variable to plot with the domain (Negative or Positive)
        removed from the beginning of the name.
    labels: list of str
        The labels for the plots
    plot_times : array_like, optional
        The times at which to plot. If None (default) the plot times will be
        the times in the comsol model.
    eval_on_edges: str, optional
        Whether the variable evaluates on edges. Default is False.
    sharex: str, optional
        Whether the colums should share axes. Default is False. Set to "col"
        so that columns share an x axes.
    """

    # Set plot times if not provided
    if plot_times is None:
        plot_times = comsol_variables["time"]

    # Process variables

    # Process pybamm variable in negative electrode
    pybamm_var_n_fun = pybamm.ProcessedVariable(
        pybamm_model.variables["Negative " + var], solution.t, solution.y, mesh=mesh
    )

    # Process pybamm variable in positive electrode
    pybamm_var_p_fun = pybamm.ProcessedVariable(
        pybamm_model.variables["Positive " + var], solution.t, solution.y, mesh=mesh
    )

    # Process comsol variable in negative electrode
    comsol_var_n_fun = pybamm.ProcessedVariable(
        comsol_model.variables["Negative " + var], solution.t, solution.y, mesh=mesh
    )

    # Process comsol variable in positive electrode
    comsol_var_p_fun = pybamm.ProcessedVariable(
        comsol_model.variables["Positive " + var], solution.t, solution.y, mesh=mesh
    )

    # Make plot
    fig, ax = plt.subplots(2, 2, sharex=sharex, figsize=(6.4, 4))
    fig.subplots_adjust(
        left=0.1, bottom=0.1, right=0.95, top=0.85, wspace=0.3, hspace=0.5
    )
    cmap = plt.get_cmap("inferno")

    # Loop over plot_times
    for ind, t in enumerate(plot_times):
        color = cmap(float(ind) / len(plot_times))

        # negative electrode
        if eval_on_edges:
            x_n = x_n_edges
        else:
            x_n = x_n_nodes
        comsol_var_n = comsol_var_n_fun(x=x_n, t=t / tau)
        pybamm_var_n = pybamm_var_n_fun(x=x_n, t=t / tau)
        ax[0, 0].plot(
            x_n[0::9] * L_x * 1e6,
            comsol_var_n[0::9],
            "o",
            color=color,
            fillstyle="none",
            label="COMSOL" if ind == 0 else "",
        )
        ax[0, 0].plot(
            x_n * L_x * 1e6,
            pybamm_var_n,
            "-",
            color=color,
            label="PyBaMM" if ind == 0 else "",
        )
        error_n = np.abs(pybamm_var_n - comsol_var_n)
        ax[1, 0].plot(x_n * L_x * 1e6, error_n, "-", color=color)

        # positive electrode
        if eval_on_edges:
            x_p = x_p_edges
        else:
            x_p = x_p_nodes
        comsol_var_p = comsol_var_p_fun(x=x_p, t=t / tau)
        pybamm_var_p = pybamm_var_p_fun(x=x_p, t=t / tau)
        ax[0, 1].plot(
            x_p[0::9] * L_x * 1e6,
            comsol_var_p[0::9],
            "o",
            color=color,
            fillstyle="none",
        )
        ax[0, 1].plot(
            x_p * L_x * 1e6, pybamm_var_p, "-", color=color, label="{:.0f} s".format(t)
        )
        error_p = np.abs(pybamm_var_p - comsol_var_p)
        ax[1, 1].plot(x_p * L_x * 1e6, error_p, "-", color=color)

    # force scientific notation outside 10^{+-2}
    ax[0, 0].ticklabel_format(style="sci", scilimits=(-2, 2), axis="y")
    ax[0, 1].ticklabel_format(style="sci", scilimits=(-2, 2), axis="y")
    ax[1, 0].ticklabel_format(style="sci", scilimits=(-2, 2), axis="y")
    ax[1, 1].ticklabel_format(style="sci", scilimits=(-2, 2), axis="y")

    # set ticks
    ax[0, 0].tick_params(which="both")
    ax[0, 1].tick_params(which="both")
    ax[1, 0].tick_params(which="both")
    ax[1, 1].tick_params(which="both")

    # set labels
    if sharex is False:
        ax[0, 0].set_xlabel(r"$x_n^*$ [$\mu$m]")
    ax[0, 0].set_ylabel(labels[0])
    if sharex is False:
        ax[0, 1].set_xlabel(r"$x_p^*$ [$\mu$m]")
    ax[0, 1].set_ylabel(labels[1])
    ax[1, 0].set_xlabel(r"$x_n^*$ [$\mu$m]")
    ax[1, 0].set_ylabel(labels[2])
    ax[1, 1].set_xlabel(r"$x_p^*$ [$\mu$m]")
    ax[1, 1].set_ylabel(labels[3])

    ax[0, 0].text(-0.1, 1.1, "(a)", transform=ax[0, 0].transAxes)
    ax[0, 1].text(-0.1, 1.1, "(b)", transform=ax[0, 1].transAxes)
    ax[1, 0].text(-0.1, 1.1, "(c)", transform=ax[1, 0].transAxes)
    ax[1, 1].text(-0.1, 1.1, "(d)", transform=ax[1, 1].transAxes)

    ax[0, 0].legend(
        bbox_to_anchor=(0, 1.2, 1.0, 0.102),
        loc="lower left",
        borderaxespad=0.0,
        ncol=2,
        mode="expand",
    )
    ax[0, 1].legend(
        bbox_to_anchor=(0, 1.2, 1.0, 0.102),
        loc="lower left",
        borderaxespad=0.0,
        ncol=3,
        mode="expand",
    )
    # plt.tight_layout()


def whole_cell_comparison_plot(
    var, labels, plot_times=None, eval_on_edges=False, sharex=False
):
    """
    Plot pybamm variable against comsol variable (both defined over whole cell)

    Parameters
    ----------

    var : str
        The name of the variable to plot.
    labels: list of str
        The labels for the plots
    plot_times : array_like, optional
        The times at which to plot. If None (default) the plot times will be
        the times in the comsol model.
    eval_on_edges: str, optional
        Whether the variable evaluates on edges. Default is False.
    sharex: str, optional
        Whether the colums should share axes. Default is False. Set to "col"
        so that columns share an x axes.
    """

    # Set plot times if not provided
    if plot_times is None:
        plot_times = comsol_variables["time"]

    # Process variables

    # Process pybamm variable
    pybamm_var_fun = pybamm.ProcessedVariable(
        pybamm_model.variables[var], solution.t, solution.y, mesh=mesh
    )

    # Process comsol variable
    comsol_var_fun = pybamm.ProcessedVariable(
        comsol_model.variables[var], solution.t, solution.y, mesh=mesh
    )

    # Make plot
    fig, ax = plt.subplots(1, 2, sharex=sharex, figsize=(6.4, 2))
    fig.subplots_adjust(left=0.1, bottom=0.2, right=0.95, top=0.7, wspace=0.3)
    cmap = plt.get_cmap("inferno")

    # Loop over plot_times
    for ind, t in enumerate(plot_times):
        color = cmap(float(ind) / len(plot_times))

        # whole cell
        if eval_on_edges:
            x = x_edges
        else:
            x = x_nodes
        comsol_var = comsol_var_fun(x=x, t=t / tau)
        pybamm_var = pybamm_var_fun(x=x, t=t / tau)
        ax[0].plot(
            x[0::8] * L_x * 1e6,
            comsol_var[0::8],
            "o",
            color=color,
            fillstyle="none",
            label="COMSOL" if ind == 0 else "",
        )
        ax[0].plot(
            x * L_x * 1e6,
            pybamm_var,
            "-",
            color=color,
            label="PyBaMM" if ind == 0 else "",
        )
        error = np.abs(pybamm_var - comsol_var)
        ax[1].plot(x * L_x * 1e6, error, "-", color=color, label="{:.0f} s".format(t))

    # force scientific notation outside 10^{+-2}
    ax[0].ticklabel_format(style="sci", scilimits=(-2, 2), axis="y")
    ax[1].ticklabel_format(style="sci", scilimits=(-2, 2), axis="y")

    # set ticks
    ax[0].tick_params(which="both")
    ax[1].tick_params(which="both")

    # set labels
    if sharex is False:
        ax[0].set_xlabel(r"$x^*$ [$\mu$m]")
    ax[0].set_ylabel(labels[0])
    ax[1].set_xlabel(r"$x^*$ [$\mu$m]")
    ax[1].set_ylabel(labels[1])

    ax[0].text(-0.1, 1.1, "(a)", transform=ax[0].transAxes)
    ax[1].text(-0.1, 1.1, "(b)", transform=ax[1].transAxes)

    ax[0].legend(
        bbox_to_anchor=(0, 1.2, 1.0, 0.102),
        loc="lower left",
        borderaxespad=0.0,
        ncol=2,
        mode="expand",
    )
    ax[1].legend(
        bbox_to_anchor=(0, 1.2, 1.0, 0.102),
        loc="lower left",
        borderaxespad=0.0,
        ncol=3,
        mode="expand",
    )


# Make plots
plot_times = [600, 1200, 1800, 2400, 3000]

# potentials
var = "electrode potential [V]"
labels = [
    r"$\phi^*_{\mathrm{s,n}}$ [V]",
    r"$\phi^*_{\mathrm{s,p}}$ [V]",
    r"$\phi^*_{\mathrm{s,n}}$ (difference) [V]",
    r"$\phi^*_{\mathrm{s,p}}$ (difference) [V]",
]
electrode_comparison_plot(var, labels, plot_times=plot_times)
var = "Electrolyte potential [V]"
labels = [r"$\phi^*_{\mathrm{e}}$ [V]", r"$\phi^*_{\mathrm{e}}$ (difference) [V]"]
whole_cell_comparison_plot(var, labels, plot_times=plot_times)

# concentrations
var = "particle surface concentration [mol.m-3]"
labels = [
    r"$c^*_{\mathrm{s,n}}$ [mol/m${}^3$]",
    r"$c^*_{\mathrm{s,p}}$ [mol/m${}^3$]",
    r"$c^*_{\mathrm{s,n}}$ (difference) [mol/m${}^3$]",
    r"$c^*_{\mathrm{s,p}}$ (difference)  [mol/m${}^3$]",
]
electrode_comparison_plot(var, labels, plot_times=plot_times)
var = "Electrolyte concentration [mol.m-3]"
labels = [
    r"$c^*_{\mathrm{e}}$ [mol/m${}^3$]",
    r"$c^*_{\mathrm{e}}$ (difference) [mol/m${}^3$]",
]
whole_cell_comparison_plot(var, labels, plot_times=plot_times)
plt.show()
