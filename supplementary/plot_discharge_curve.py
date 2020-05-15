import pybamm
import pickle
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import scipy.interpolate as interp

# set style
matplotlib.rc_file("_matplotlibrc", use_default_template=True)

pybamm.set_logging_level("INFO")

"-----------------------------------------------------------------------------"
"Set up figure"

sharex = False  # set to "col" to have columns share x axes
fig, ax = plt.subplots(2, 2, sharex=sharex, figsize=(6.4, 4))
fig.subplots_adjust(left=0.1, bottom=0.1, right=0.8, top=0.9, wspace=0.5, hspace=0.5)

ax[0, 0].text(-0.1, 1.1, "(a)", transform=ax[0, 0].transAxes)
if sharex is False:
    ax[0, 0].set_xlabel("Discharge Capacity [Ah]")
ax[0, 0].set_ylabel("Terminal voltage [V]")
ax[0, 1].text(-0.1, 1.1, "(b)", transform=ax[0, 1].transAxes)
if sharex is False:
    ax[0, 1].set_xlabel("Discharge Capacity [Ah]")
ax[0, 1].set_ylabel("Temperature [K]")
ax[1, 0].text(-0.1, 1.1, "(c)", transform=ax[1, 0].transAxes)
ax[1, 0].set_xlabel("Discharge Capacity [Ah]")
ax[1, 0].set_ylabel("Difference [V]")
ax[1, 0].set_yscale("log")
ax[1, 1].text(-0.1, 1.1, "(d)", transform=ax[1, 1].transAxes)
ax[1, 1].set_xlabel("Discharge Capacity [Ah]")
ax[1, 1].set_ylabel("Difference [K]")


"-----------------------------------------------------------------------------"
"Build PyBamm Model"
C_rates = {"05": 0.5, "1": 1, "2": 2, "3": 3}

# load model and geometry
options = {"thermal": "x-full"}
pybamm_model = pybamm.lithium_ion.DFN(options)
geometry = pybamm_model.default_geometry

# load parameters and process model and geometry
param = pybamm_model.default_parameter_values
param.process_model(pybamm_model)
param.process_geometry(geometry)

# create mesh
var = pybamm.standard_spatial_vars
var_pts = {var.x_n: 128, var.x_s: 128, var.x_p: 128, var.r_n: 128, var.r_p: 128}
mesh = pybamm.Mesh(geometry, pybamm_model.default_submesh_types, var_pts)

# discretise model
spatial_methods = pybamm_model.default_spatial_methods
disc = pybamm.Discretisation(mesh, pybamm_model.default_spatial_methods)
disc.process_model(pybamm_model, check_model=False)

# solver
solver = pybamm.CasadiSolver(atol=1e-6, rtol=1e-6, root_tol=1e-6, mode="fast")

"-----------------------------------------------------------------------------"
"Solve at different C_rates and plot against COMSOL solution"

counter = 0
interp_kind = "cubic"

for key, value in C_rates.items():
    # load comsol_model
    comsol_variables = pickle.load(
        open("comsol_data/comsol_1D_{}C.pickle".format(key), "rb")
    )
    comsol_t = comsol_variables["time"]
    comsol_voltage = interp.interp1d(
        comsol_t, comsol_variables["voltage"], kind=interp_kind
    )
    comsol_temperature = interp.interp1d(
        comsol_t, comsol_variables["average temperature"], kind=interp_kind
    )

    # update C_rate
    param.update({"C-rate": value})
    param.update_model(pybamm_model, disc)

    # solve
    tau = param.evaluate(pybamm.standard_parameters_lithium_ion.tau_discharge)
    time = comsol_t / tau  # use comsol time
    solution = solver.solve(pybamm_model, time)
    time = solution.t

    # plot using times up to voltage cut off
    # Note: casadi doesnt support events so we find this time after the solve
    if isinstance(solver, pybamm.CasadiSolver):
        V_cutoff = param.evaluate(
            pybamm.standard_parameters_lithium_ion.voltage_low_cut_dimensional
        )
        voltage = pybamm.ProcessedVariable(
            pybamm_model.variables["Terminal voltage [V]"],
            solution.t,
            solution.y,
            mesh=mesh,
        )(time)
        # only use times up to the voltage cutoff
        voltage_OK = voltage[voltage > V_cutoff]
        time = time[0 : len(voltage_OK)]

    # post-process pybamm solution
    pybamm_voltage = pybamm.ProcessedVariable(
        pybamm_model.variables["Terminal voltage [V]"], solution.t, solution.y, mesh
    )(t=time)
    pybamm_temperature = pybamm.ProcessedVariable(
        pybamm_model.variables["Volume-averaged cell temperature [K]"],
        solution.t,
        solution.y,
        mesh,
    )(t=time)

    # compute discharge_capacity
    dis_cap = pybamm.ProcessedVariable(
        pybamm_model.variables["Discharge capacity [A.h]"], solution.t, solution.y, mesh
    )(t=time)

    # add to plot
    ax[0, 0].plot(
        dis_cap[0::25],
        comsol_voltage(time[0::25] * tau),
        "o",
        fillstyle="none",
        color="C{}".format(counter),
        label="COMSOL" if counter == 0 else "",
    )
    ax[0, 0].plot(
        dis_cap,
        pybamm_voltage,
        "-",
        color="C{}".format(counter),
        label="PyBaMM ({}C)".format(value),
    )
    ax[0, 1].plot(
        dis_cap[0::25],
        comsol_temperature(time[0::25] * tau),
        "o",
        fillstyle="none",
        color="C{}".format(counter),
        label="COMSOL" if counter == 0 else "",
    )
    ax[0, 1].plot(
        dis_cap,
        pybamm_temperature,
        "-",
        color="C{}".format(counter),
        label="PyBaMM ({}C)".format(value),
    )
    ax[1, 0].plot(
        dis_cap,
        np.abs(pybamm_voltage - comsol_voltage(time * tau)),
        "-",
        color="C{}".format(counter),
        label="{}C".format(value),
    )
    ax[1, 1].plot(
        dis_cap,
        np.abs(pybamm_temperature - comsol_temperature(time * tau)),
        "-",
        color="C{}".format(counter),
        label="{}C".format(value),
    )

    # increase counter for labelling
    counter += 1

"-----------------------------------------------------------------------------"
"Add legend and show plot"

ax[0, 1].legend(bbox_to_anchor=(1.04, 1), loc="upper left", borderaxespad=0.0)
ax[1, 1].legend(bbox_to_anchor=(1.04, 1), loc="upper left", borderaxespad=0.0)
plt.show()
