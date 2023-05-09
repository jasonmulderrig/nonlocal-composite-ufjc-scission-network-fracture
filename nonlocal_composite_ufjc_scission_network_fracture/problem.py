# import necessary libraries
from __future__ import division
from dolfin import *
from .default_parameters import default_parameters
from .composite_ufjc_network import CompositeuFJCNetwork
from .utility import (
    generate_savedir,
    print0,
    peval,
    local_project,
    max_ufl_fenics_mesh_func
)
import sys
from copy import deepcopy

class TwoDimensionalPlaneStrainNearlyIncompressibleNonaffineEightChainModelEqualStrainRateIndependentCompositeuFJCNetworkNonlocalScissionNetworkFractureProblem(object):
    """
    Problem class for composite uFJC networks with non-local scission
    leading to macroscopic fracture. The composite uFJC network here
    exhibits the following characteristics (as indicated by the class
    name):
    -> Physical dimensionality: Two-dimensional
    -> Two-dimensional formulation: Plane strain
    -> Incompressibility assumption: Nearly-incompressible
    -> Macro-to-micro deformation assumption: Nonaffine
    -> Micro-to-macro homogenizatio scheme: Eight-chain model
    -> Chain-level load sharing assumption: Equal strain
    -> Chain scission rate-dependence: Rate-independent
    """
    def __init__(self):

        # Set the mpi communicator of the object
        self.comm_rank = MPI.rank(MPI.comm_world)
        self.comm_size = MPI.size(MPI.comm_world)

        # Parameters
        self.parameters = default_parameters()
        self.set_user_parameters()
        self.set_user_parameters_in_lists()
        self.set_user_parameters_in_dicts()
        self.set_user_modelname()

        # Setup filesystem
        self.savedir = generate_savedir(self.prefix())

        # Pre-processing
        ppp = self.parameters["pre_processing"]
        set_log_level(LogLevel.WARNING)
        parameters["form_compiler"]["optimize"] = ppp["form_compiler_optimize"]
        parameters["form_compiler"]["cpp_optimize"] = ppp["form_compiler_cpp_optimize"]
        parameters["form_compiler"]["representation"] = ppp["form_compiler_representation"]
        parameters["form_compiler"]["quadrature_degree"] = ppp["form_compiler_quadrature_degree"]
        info(parameters, True)

        # Mesh
        self.mesh = self.define_mesh()
        self.dimension = self.mesh.geometry().dim() # spatial dimensions of the mesh

        # MeshFunctions and Measures for different blocks and boundaries; may not need this functionality
        self.set_mesh_functions()
        self.set_measures()

        # Material
        mp = self.parameters["material"]
        self.material = CompositeuFJCNetwork(mp)

        # Variational formulation
        self.set_variational_formulation()

        # Set boundary conditions
        self.define_bcs()

        # Deformation
        self.set_applied_deformation()

        # Post-processing
        self.set_post_processing()

        # Solver set up
        self.solver_setup()
    
    def set_user_parameters(self):
        """
        Set the user parameters defining the problem
        """
        pass

    def set_user_parameters_in_lists(self):
        """
        Recast and define particular parameters as attributes in Python
        lists
        """
        gp = self.parameters["two_dimensional_geometry"]
        mp = self.parameters["material"]
        
        # Meshpoints
        self.meshpoint_num = gp["meshpoint_num"]
        meshpoints_list = []
        meshpoints_label_list = []
        meshpoints_color_list = []
        meshpoints_name_list = []

        for meshpoint_indx in range(self.meshpoint_num):
            meshpoint_x_coord = gp["meshpoint_indx_"+str(meshpoint_indx)+"_x_coord"]
            meshpoint_y_coord = gp["meshpoint_indx_"+str(meshpoint_indx)+"_y_coord"]
            meshpoints_label = gp["meshpoint_indx_"+str(meshpoint_indx)+"_label"]
            meshpoints_color = gp["meshpoint_indx_"+str(meshpoint_indx)+"_color"]
            meshpoints_name = gp["meshpoint_indx_"+str(meshpoint_indx)+"_name"]

            meshpoint = (meshpoint_x_coord, meshpoint_y_coord)

            meshpoints_list.append(meshpoint)
            meshpoints_label_list.append(meshpoints_label)
            meshpoints_color_list.append(meshpoints_color)
            meshpoints_name_list.append(meshpoints_name)
        
        self.meshpoints_list = meshpoints_list
        self.meshpoints_label_list = meshpoints_label_list
        self.meshpoints_color_list = meshpoints_color_list
        self.meshpoints_name_list = meshpoints_name_list

        # Chain segment numbers
        self.nu_num = mp["nu_num"]
        nu_list = []

        for nu_indx in range(self.nu_num):
            nu_val = mp["nu_indx_"+str(nu_indx)+"_nu_val"]
            nu_list.append(nu_val)
        
        self.nu_list = nu_list

        # Chain segment number chunks
        self.nu_chunks_num = mp["nu_chunks_num"]
        nu_chunks_list = []
        nu_chunks_indx_in_nu_list = []
        nu_chunks_label_list = []
        nu_chunks_color_list = []

        for nu_chunk_indx in range(self.nu_chunks_num):
            nu_chunks_val = mp["nu_chunk_indx_"+str(nu_chunk_indx)+"_nu_val"]
            nu_chunks_indx_val_in_nu_list = mp["nu_chunk_indx_"+str(nu_chunk_indx)+"_indx_val_in_nu_list"]
            nu_chunks_label = mp["nu_chunk_indx_"+str(nu_chunk_indx)+"_label"]
            nu_chunks_color = mp["nu_chunk_indx_"+str(nu_chunk_indx)+"_color"]

            nu_chunks_list.append(nu_chunks_val)
            nu_chunks_indx_in_nu_list.append(nu_chunks_indx_val_in_nu_list)
            nu_chunks_label_list.append(nu_chunks_label)
            nu_chunks_color_list.append(nu_chunks_color)
        
        self.nu_chunks_list = nu_chunks_list
        self.nu_chunks_indx_in_nu_list = nu_chunks_indx_in_nu_list
        self.nu_chunks_label_list = nu_chunks_label_list
        self.nu_chunks_color_list = nu_chunks_color_list
    
    def set_user_parameters_in_dicts(self):
        """
        Recast and define particular parameters as attributes in Python
        dictionaries
        """
        femp = self.parameters["fem"]

        # Metadata quadrature degree
        self.metadata  = {"quadrature_degree": femp["quadrature_degree"]}

        self.two_dim_vector_indx_dict = {
            "1": 0,
            "2": 1
        }

        # Tensor-to-Voigt notation dictionary
        self.two_dim_tensor2voigt_vector_indx_dict = {
            "11": 0,
            "12": 1,
            "21": 2,
            "22": 3
        }

        # Dictionaries for solver parameters
        # solver_u
        self.solver_u_parameters_dict = {"nonlinear_solver": "snes",
                                         "symmetric": True,
                                         "snes_solver": {"linear_solver": "mumps",
                                                         "method": "newtontr",
                                                         "line_search": "cp",
                                                         "preconditioner": "hypre_amg",
                                                         "maximum_iterations": 200,
                                                         "absolute_tolerance": 1e-8,
                                                         "relative_tolerance": 1e-7,
                                                         "solution_tolerance": 1e-7,
                                                         "report": True,
                                                         "error_on_nonconvergence": False
                                                         }
                                                         }

        # solver_bounded_lmbda_c_tilde
        self.solver_bounded_lmbda_c_tilde_parameters_dict = {"nonlinear_solver": "snes",
                                                             "symmetric": True,
                                                             "snes_solver": {"linear_solver": "umfpack",
                                                                             "method": "vinewtonssls",
                                                                             "line_search": "basic",
                                                                             "maximum_iterations": 50,
                                                                             "absolute_tolerance": 1e-8,
                                                                             "relative_tolerance": 1e-5,
                                                                             "solution_tolerance": 1e-5,
                                                                             "report": True,
                                                                             "error_on_nonconvergence": False
                                                                             }
                                                                             }

        # solver_unbounded_lmbda_c_tilde
        self.solver_unbounded_lmbda_c_tilde_parameters_dict = {"nonlinear_solver": "snes",
                                                               "symmetric": True,
                                                               "snes_solver": {"linear_solver": "mumps",
                                                                               "method": "newtontr",
                                                                               "line_search": "cp",
                                                                               "preconditioner": "hypre_amg",
                                                                               "maximum_iterations": 200,
                                                                               "absolute_tolerance": 1e-8,
                                                                               "relative_tolerance": 1e-7,
                                                                               "solution_tolerance": 1e-7,
                                                                               "report": True,
                                                                               "error_on_nonconvergence": False
                                                                               }
                                                                               }

        # solver_bounded_monolithic
        self.solver_bounded_monolithic_parameters_dict = {"nonlinear_solver": "snes",
                                                          "symmetric": True,
                                                          "snes_solver": {"linear_solver": "umfpack",
                                                                          "method": "vinewtonssls",
                                                                          "line_search": "basic",
                                                                          "maximum_iterations": 50,
                                                                          "absolute_tolerance": 1e-8,
                                                                          "relative_tolerance": 1e-5,
                                                                          "solution_tolerance": 1e-5,
                                                                          "report": True,
                                                                          "error_on_nonconvergence": False
                                                                          }
                                                                          }

        # solver_unbounded_monolithic
        self.solver_unbounded_monolithic_parameters_dict = {"nonlinear_solver": "snes",
                                                            "symmetric": True,
                                                            "snes_solver": {"linear_solver": "mumps",
                                                                            "method": "newtontr",
                                                                            "line_search": "cp",
                                                                            "preconditioner": "hypre_amg",
                                                                            "maximum_iterations": 200,
                                                                            "absolute_tolerance": 1e-8,
                                                                            "relative_tolerance": 1e-7,
                                                                            "solution_tolerance": 1e-7,
                                                                            "report": True,
                                                                            "error_on_nonconvergence": False
                                                                            }
                                                                            }
    
    def set_user_modelname(self):
        mp = self.parameters["material"]

        self.modelname = (
            mp["physical_dimensionality"]
            + "_" + mp["two_dimensional_formulation"]
            + "_" + mp["incompressibility_assumption"]
            + "_" + mp["macro2micro_deformation_assumption"]
            + "_" + mp["micro2macro_homogenization_scheme"]
            + "_" + mp["chain_level_load_sharing"]
            + "_" + mp["rate_dependence"]
        )
    
    def prefix(self):
        return self.modelname + "_" + "problem"

    def define_mesh(self):
        """
        Define the mesh for the problem
        """
        pass

    def set_mesh_functions(self):
        """
        Set meshfunctions with boundaries and subdomain indicators
        """
        # self.fem.cells_meshfunction = MeshFunction("size_t", self.fem.mesh, self.fem.dimension)
        # self.fem.cells_meshfunction.set_all(0)
        # self.fem.exterior_facets_meshfunction = MeshFunction("size_t", self.fem.mesh, self.fem.dimension-1)
        # self.fem.exterior_facets_meshfunction.set_all(0)
        pass
    
    def set_measures(self):
        """
        Assign the Measure to get selective integration on boundaries and bulk subdomain
        The Measure is defined using self.fem.cells_meshfunction and self.fem.exterior_facets_meshfunction
        """
        # try:
        #     self.dx = Measure("dx")(subdomain_data=self.cells_meshfunction)
        # except:
        #     self.dx = dx
        # try:
        #     self.ds = Measure("ds")(subdomain_data=self.exterior_facets_meshfunction)
        # except:
        #     self.ds = ds
        pass

    def set_variational_formulation(self):
        """
        Define the variational formulation problem to be solved
        """
        femp = self.parameters["fem"]

        if femp["solver_algorithm"] == "alternate_minimization":
            self.set_alternate_minimization_variational_formulation()
        
        elif femp["solver_algorithm"] == "monolithic":
            self.set_monolithic_variational_formulation()
    
    def set_alternate_minimization_variational_formulation(self):
        """
        Define the variational formulation problem to be solved using
        the alternate minimization solution scheme
        """
        femp = self.parameters["fem"]
        mp = self.parameters["material"]
        ppp = self.parameters["post_processing"]

        # Create function space for displacement
        self.V_u = VectorFunctionSpace(self.mesh, "CG", femp["u_degree"])
        # Create function space for non-local chain stretch
        self.V_lmbda_c_tilde = FunctionSpace(self.mesh, "CG", femp["scalar_prmtr_degree"])

        # Define solution, trial, and test functions, respectively, for displacement
        self.u   = Function(self.V_u)
        self.du  = TrialFunction(self.V_u)
        self.v_u = TestFunction(self.V_u)

        # Define solution, trial, and test functions, respectively, for non-local chain stretch
        self.lmbda_c_tilde   = Function(self.V_lmbda_c_tilde)
        self.dlmbda_c_tilde  = TrialFunction(self.V_lmbda_c_tilde)
        self.v_lmbda_c_tilde = TestFunction(self.V_lmbda_c_tilde)

        # Initialization
        self.lmbda_c_tilde = interpolate(Expression("1.", degree=femp["scalar_prmtr_degree"]), self.V_lmbda_c_tilde)
        self.lmbda_c_tilde_prior = interpolate(Expression("1.", degree=femp["scalar_prmtr_degree"]), self.V_lmbda_c_tilde)
        self.lmbda_c_tilde_max = interpolate(Expression("1.", degree=femp["scalar_prmtr_degree"]), self.V_lmbda_c_tilde)

        if femp["solver_bounded"]:
            # Initialization
            self.lmbda_c_tilde_lb = interpolate(Expression("1.", degree=femp["scalar_prmtr_degree"]), self.V_lmbda_c_tilde)
            # The upper-bound is technically (+)infinity
            self.lmbda_c_tilde_ub = interpolate(Expression("10000.0", degree=femp["scalar_prmtr_degree"]), self.V_lmbda_c_tilde)
        
        # Define objects needed for calculations
        self.I           = Identity(len(self.u))
        self.V_CG_scalar = FunctionSpace(self.mesh, "CG", femp["scalar_prmtr_degree"])
        self.V_DG_scalar = FunctionSpace(self.mesh, "DG", femp["scalar_prmtr_degree"])
        self.V_DG_tensor = TensorFunctionSpace(self.mesh, "DG", 0)

        if ppp["save_lmbda_c_mesh"] or ppp["save_lmbda_c_chunks"]:
            self.V_lmbda_c = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_c_eq_mesh"] or ppp["save_lmbda_c_eq_chunks"]:
            self.V_lmbda_c_eq = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_nu_mesh"] or ppp["save_lmbda_nu_chunks"]:
            self.V_lmbda_nu = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_c_eq_tilde_mesh"] or ppp["save_lmbda_c_eq_tilde_chunks"]:
            self.V_lmbda_c_eq_tilde = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_nu_tilde_mesh"] or ppp["save_lmbda_nu_tilde_chunks"]:
            self.V_lmbda_nu_tilde = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_c_eq_tilde_max_mesh"] or ppp["save_lmbda_c_eq_tilde_max_chunks"]:
            self.V_lmbda_c_eq_tilde_max = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_nu_tilde_max_mesh"] or ppp["save_lmbda_nu_tilde_max_chunks"]:
            self.V_lmbda_nu_tilde_max = Function(self.V_DG_scalar)
        
        if ppp["save_upsilon_c_mesh"] or ppp["save_upsilon_c_chunks"]:
            self.V_upsilon_c = Function(self.V_DG_scalar)
        
        if ppp["save_Upsilon_c_mesh"] or ppp["save_Upsilon_c_chunks"]:
            self.V_Upsilon_c = Function(self.V_DG_scalar)
        
        if ppp["save_d_c_mesh"] or ppp["save_d_c_chunks"]:
            self.V_d_c = Function(self.V_DG_scalar)
        
        if ppp["save_D_c_mesh"] or ppp["save_D_c_chunks"]:
            self.V_D_c = Function(self.V_DG_scalar)
        
        if ppp["save_epsilon_cnu_diss_hat_mesh"] or ppp["save_epsilon_cnu_diss_hat_chunks"]:
            self.V_epsilon_cnu_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_Epsilon_cnu_diss_hat_mesh"] or ppp["save_Epsilon_cnu_diss_hat_chunks"]:
            self.V_Epsilon_cnu_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_epsilon_c_diss_hat_mesh"] or ppp["save_epsilon_c_diss_hat_chunks"]:
            self.V_epsilon_c_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_Epsilon_c_diss_hat_mesh"] or ppp["save_Epsilon_c_diss_hat_chunks"]:
            self.V_Epsilon_c_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_overline_epsilon_cnu_diss_hat_mesh"] or ppp["save_overline_epsilon_cnu_diss_hat_chunks"]:
            self.V_overline_epsilon_cnu_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_overline_Epsilon_cnu_diss_hat_mesh"] or ppp["save_overline_Epsilon_cnu_diss_hat_chunks"]:
            self.V_overline_Epsilon_cnu_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_overline_epsilon_c_diss_hat_mesh"] or ppp["save_overline_epsilon_c_diss_hat_chunks"]:
            self.V_overline_epsilon_c_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_overline_Epsilon_c_diss_hat_mesh"] or ppp["save_overline_Epsilon_c_diss_hat_chunks"]:
            self.V_overline_Epsilon_c_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_F_mesh"] or ppp["save_F_chunks"]:
            self.V_F = Function(self.V_DG_tensor)
        
        if ppp["save_sigma_mesh"] or ppp["save_sigma_chunks"]:
            self.V_sigma = Function(self.V_DG_tensor)
            self.V_sigma_penalty_term = Function(self.V_DG_tensor)
            self.V_sigma_less_penalty_term = Function(self.V_DG_tensor)

        # Kinematics
        # deformation gradient tensor
        self.F = self.I + grad(self.u)
        # inverse deformation gradient tensor
        self.F_inv = inv(self.F)
        # volume ratio
        self.J = det(self.F)
        # right Cauchy-Green tensor
        self.C = self.F.T*self.F
        # 2D plane strain form of the trace of right Cauchy-Green
        # tensor, where F_33 = 1 always
        self.I_C = tr(self.C)+1
        # local chain stretch
        self.lmbda_c = sqrt(self.I_C/3.0)

        # Define body force and traction force
        self.b_hat = Constant((0.0, 0.0)) # Body force per unit volume
        self.t_hat = Constant((0.0, 0.0)) # Traction force on the boundary

        # Define gradient activity and normalized anisotropic
        # interaction tensor
        self.g = Constant(1.)
        self.H_tilde = self.I

        # Calculate the weak form for displacement
        self.WF_u = (
            inner(self.first_pk_stress_ufl_fenics_mesh_func(), grad(self.v_u))*dx(metadata=self.metadata)
            - dot(self.b_hat, self.v_u)*dx(metadata=self.metadata)
            - dot(self.t_hat, self.v_u)*ds
        )

        # Calculate the Gateaux derivative for displacement
        self.Jac_u = derivative(self.WF_u, self.u, self.du)

        # Calculate the weak form for non-local chain stretch
        self.WF_lmbda_c_tilde = (
            self.v_lmbda_c_tilde*self.lmbda_c_tilde*dx(metadata=self.metadata)
            + mp["l_nl"]**2*self.g*dot(grad(self.v_lmbda_c_tilde), self.H_tilde*grad(self.lmbda_c_tilde))*dx(metadata=self.metadata)
            - self.v_lmbda_c_tilde*self.lmbda_c*dx(metadata=self.metadata)
        )

        # Calculate the Gateaux derivative for non-local chain stretch
        self.Jac_lmbda_c_tilde = derivative(self.WF_lmbda_c_tilde, self.lmbda_c_tilde, self.dlmbda_c_tilde)
    
    def set_monolithic_variational_formulation(self):
        """
        Define the variational formulation problem to be solved using
        the monolithic solution scheme
        """
        femp = self.parameters["fem"]
        mp = self.parameters["material"]
        ppp = self.parameters["post_processing"]

        # Create function space for displacement
        self.V_u = VectorFunctionSpace(self.mesh, "CG", femp["u_degree"])
        # Create function space for non-local chain stretch
        self.V_lmbda_c_tilde = FunctionSpace(self.mesh, "CG", femp["scalar_prmtr_degree"])

        # Create UFL element from the displacement function space
        self.V_u_ufl_elem = self.V_u.ufl_element()
        # Create UFL element from the non-local chain stretch function space
        self.V_lmbda_c_tilde_ufl_elem = self.V_lmbda_c_tilde.ufl_element()
        # Create UFL mixed element
        self.mixed_ufl_elem = MixedElement([self.V_u_ufl_elem, self.V_lmbda_c_tilde_ufl_elem])
        # Define function space for the UFL mixed element
        self.V = FunctionSpace(self.mesh, self.mixed_ufl_elem)

        # Define solution, trial, and test functions for the UFL mixed element
        self.mixed_space = Function(self.V)
        self.dmixed_space = TrialFunction(self.V)
        self.v_mixed_space = TestFunction(self.V)

        # Split the mixed function space and the mixed test function space for displacement and non-local chain stretch
        (self.u, self.lmbda_c_tilde) = split(self.mixed_space)
        (self.v_u, self.v_lmbda_c_tilde) = split(self.v_mixed_space)

        # Initialization
        class InitialConditions(UserExpression):
            def eval(self, vals, x):
                vals[0] = 0.0 # u_x
                vals[1] = 0.0 # u_y
                vals[2] = 1.0 # lambda_c_tilde
            def value_shape(self):
                return (3,)
        
        mixed_space_degree = femp["u_degree"]
        ics = InitialConditions(degree=mixed_space_degree)
        self.mixed_space.interpolate(ics)

        self.lmbda_c_tilde_max = interpolate(Expression("0.", degree=femp["scalar_prmtr_degree"]), self.V_lmbda_c_tilde)

        # Define objects needed for calculations
        self.I           = Identity(len(self.u))
        self.V_CG_scalar = FunctionSpace(self.mesh, "CG", femp["scalar_prmtr_degree"])
        self.V_DG_scalar = FunctionSpace(self.mesh, "DG", femp["scalar_prmtr_degree"])
        self.V_DG_tensor = TensorFunctionSpace(self.mesh, "DG", 0)
        
        if ppp["save_lmbda_c_mesh"] or ppp["save_lmbda_c_chunks"]:
            self.V_lmbda_c = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_c_eq_mesh"] or ppp["save_lmbda_c_eq_chunks"]:
            self.V_lmbda_c_eq = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_nu_mesh"] or ppp["save_lmbda_nu_chunks"]:
            self.V_lmbda_nu = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_c_eq_tilde_mesh"] or ppp["save_lmbda_c_eq_tilde_chunks"]:
            self.V_lmbda_c_eq_tilde = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_nu_tilde_mesh"] or ppp["save_lmbda_nu_tilde_chunks"]:
            self.V_lmbda_nu_tilde = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_c_eq_tilde_max_mesh"] or ppp["save_lmbda_c_eq_tilde_max_chunks"]:
            self.V_lmbda_c_eq_tilde_max = Function(self.V_DG_scalar)
        
        if ppp["save_lmbda_nu_tilde_max_mesh"] or ppp["save_lmbda_nu_tilde_max_chunks"]:
            self.V_lmbda_nu_tilde_max = Function(self.V_DG_scalar)
        
        if ppp["save_upsilon_c_mesh"] or ppp["save_upsilon_c_chunks"]:
            self.V_upsilon_c = Function(self.V_DG_scalar)
        
        if ppp["save_Upsilon_c_mesh"] or ppp["save_Upsilon_c_chunks"]:
            self.V_Upsilon_c = Function(self.V_DG_scalar)
        
        if ppp["save_d_c_mesh"] or ppp["save_d_c_chunks"]:
            self.V_d_c = Function(self.V_DG_scalar)
        
        if ppp["save_D_c_mesh"] or ppp["save_D_c_chunks"]:
            self.V_D_c = Function(self.V_DG_scalar)
        
        if ppp["save_epsilon_cnu_diss_hat_mesh"] or ppp["save_epsilon_cnu_diss_hat_chunks"]:
            self.V_epsilon_cnu_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_Epsilon_cnu_diss_hat_mesh"] or ppp["save_Epsilon_cnu_diss_hat_chunks"]:
            self.V_Epsilon_cnu_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_epsilon_c_diss_hat_mesh"] or ppp["save_epsilon_c_diss_hat_chunks"]:
            self.V_epsilon_c_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_Epsilon_c_diss_hat_mesh"] or ppp["save_Epsilon_c_diss_hat_chunks"]:
            self.V_Epsilon_c_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_overline_epsilon_cnu_diss_hat_mesh"] or ppp["save_overline_epsilon_cnu_diss_hat_chunks"]:
            self.V_overline_epsilon_cnu_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_overline_Epsilon_cnu_diss_hat_mesh"] or ppp["save_overline_Epsilon_cnu_diss_hat_chunks"]:
            self.V_overline_Epsilon_cnu_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_overline_epsilon_c_diss_hat_mesh"] or ppp["save_overline_epsilon_c_diss_hat_chunks"]:
            self.V_overline_epsilon_c_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_overline_Epsilon_c_diss_hat_mesh"] or ppp["save_overline_Epsilon_c_diss_hat_chunks"]:
            self.V_overline_Epsilon_c_diss_hat = Function(self.V_DG_scalar)
        
        if ppp["save_F_mesh"] or ppp["save_F_chunks"]:
            self.V_F = Function(self.V_DG_tensor)
        
        if ppp["save_sigma_mesh"] or ppp["save_sigma_chunks"]:
            self.V_sigma = Function(self.V_DG_tensor)
            self.V_sigma_penalty_term = Function(self.V_DG_tensor)
            self.V_sigma_less_penalty_term = Function(self.V_DG_tensor)

        # Kinematics
        # deformation gradient tensor
        self.F = self.I + grad(self.u)
        # inverse deformation gradient tensor
        self.F_inv = inv(self.F)
        # volume ratio
        self.J = det(self.F)
        # right Cauchy-Green tensor
        self.C = self.F.T*self.F
        # 2D plane strain form of the trace of right Cauchy-Green
        # tensor, where F_33 = 1 always
        self.I_C = tr(self.C)+1
        # local chain stretch
        self.lmbda_c = sqrt(self.I_C/3.0)
    
        # Define body force and traction force
        self.b_hat = Constant((0.0, 0.0)) # Body force per unit volume
        self.t_hat = Constant((0.0, 0.0)) # Traction force on the boundary

        # Define gradient activity and normalized anisotropic
        # interaction tensor
        self.g = Constant(1.)
        self.H_tilde = self.I

        # Calculate the weak form for displacement
        self.WF_u = (
            inner(self.first_pk_stress_ufl_fenics_mesh_func(), grad(self.v_u))*dx(metadata=self.metadata)
            - dot(self.b_hat, self.v_u)*dx(metadata=self.metadata)
            - dot(self.t_hat, self.v_u)*ds
        )

        # Calculate the weak form for non-local chain stretch
        self.WF_lmbda_c_tilde = (
            self.v_lmbda_c_tilde*self.lmbda_c_tilde*dx(metadata=self.metadata)
            + mp["l_nl"]**2*self.g*dot(grad(self.v_lmbda_c_tilde), self.H_tilde*grad(self.lmbda_c_tilde))*dx(metadata=self.metadata)
            - self.v_lmbda_c_tilde*self.lmbda_c*dx(metadata=self.metadata)
        )

        # Calculate the overall weak form
        self.WF = self.WF_u + self.WF_lmbda_c_tilde

        # Calculate the Gateaux derivative
        self.Jac = derivative(self.WF, self.mixed_space, self.dmixed_space)
    
    def define_bcs(self):
        """
        Define boundary conditions by returning a list, or several
        lists, of boundary conditions
        """
        femp = self.parameters["fem"]

        if femp["solver_algorithm"] == "alternate_minimization":
            self.define_bc_alternate_minimization()
        
        elif femp["solver_algorithm"] == "monolithic":
            self.bc_monolithic = self.define_bc_monolithic()
    
    def define_bc_alternate_minimization(self):
        """
        Define boundary conditions for the alternate minimization
        solution scheme by returning a list of boundary conditions on
        the displacement and another list of boundary conditions on the
        non-local chain stretch
        """
        self.bc_u = self.define_bc_u()
        self.bc_lmbda_c_tilde = self.define_bc_lmbda_c_tilde()
    
    def define_bc_u(self):
        """
        Return a list of boundary conditions on the displacement
        """
        return []
    
    def define_bc_lmbda_c_tilde(self):
        """
        Return a list of boundary conditions on the non-local chain
        stretch
        """
        return []
    
    def define_bc_monolithic(self):
        """
        Return a list of boundary conditions for the monolithic solution
        scheme
        """
        return []
    
    def set_applied_deformation(self):
        """
        Set the applied deformation history
        """
        dp = self.parameters["deformation"]
        cond_val = 1e-8
        
        if dp["t_step"] > dp["t_max"]:
            error_message = """\
                Error: The time step is larger than the total \
                deformation time!
                """
            sys.exit(error_message)

        # Initialize the chunk counter and associated constants/lists
        chunk_counter  = 0
        chunk_indx_val = 0
        chunk_indx     = []

        # Initialization step
        t_val    = dp["t_min"] # sec
        t        = [] # sec
        t_chunks = [] # sec
        lmbda    = self.initialize_lmbda()

        # Append to appropriate lists
        t.append(t_val)
        t_chunks.append(t_val)
        chunk_indx.append(chunk_indx_val)
        lmbda = self.store_initialized_lmbda(lmbda)

        # Update the chunk iteration counter
        chunk_counter  += 1
        chunk_indx_val += 1

        # Advance to the first time step
        t_val += dp["t_step"]

        while t_val <= (dp["t_max"]+cond_val):
            # Calculate displacement at a particular time step
            lmbda_val = self.calculate_lmbda_func(t_val)

            # Append to appropriate lists
            t.append(t_val)
            lmbda = self.store_calculated_lmbda(lmbda, lmbda_val)

            if chunk_counter == dp["t_step_chunk_num"]:
                # Append to appropriate lists
                t_chunks.append(t_val)
                chunk_indx.append(chunk_indx_val)
                lmbda = self.store_calculated_lmbda_chunk_post_processing(lmbda, lmbda_val)

                # Update the time step chunk iteration counter
                chunk_counter = 0

            # Advance to the next time step
            t_val          += dp["t_step"]
            chunk_counter  += 1
            chunk_indx_val += 1
        
        u = self.calculate_u_func(lmbda)

        # If the endpoint of the chunked applied deformation is not
        # equal to the true endpoint of the applied deformation, then
        # give the user the option to kill the simulation, or proceed on
        if chunk_indx[-1] != len(t)-1:
            error_message = """\
                The endpoint of the chunked applied deformation is not \
                equal to the endpoint of the actual applied deformation. \
                Do you wish to kill the simulation here? If so, say yes. \
                If not, the simulation will proceed on.
                """
            terminal_statement = input(error_message)
            if terminal_statement.lower() == 'yes':
                sys.exit()
            else: pass
        
        self.t          = t
        self.t_chunks   = t_chunks
        self.chunk_indx = chunk_indx
        self.save_deformation_attributes(lmbda, u)
    
    def F_func(self, t):
        """
        Function defining the deformation
        """
        dp = self.parameters["deformation"]

        return 1 + dp["strain_rate"]*(t-dp["t_min"])
    
    def initialize_lmbda(self):
        lmbda_x        = [] # unitless
        lmbda_x_chunks = [] # unitless

        return lmbda_x, lmbda_x_chunks
    
    def store_initialized_lmbda(self, lmbda):
        lmbda_x_val = 1 # assuming no pre-stretching
        
        lmbda_x        = lmbda[0]
        lmbda_x_chunks = lmbda[1]
        
        lmbda_x.append(lmbda_x_val)
        lmbda_x_chunks.append(lmbda_x_val)
        
        return lmbda_x, lmbda_x_chunks
    
    def calculate_lmbda_func(self, t_val):
        lmbda_x_val = self.F_func(t_val)

        return lmbda_x_val
    
    def store_calculated_lmbda(self, lmbda, lmbda_val):
        lmbda_x        = lmbda[0]
        lmbda_x_chunks = lmbda[1]
        lmbda_x_val    = lmbda_val
        
        lmbda_x.append(lmbda_x_val)
        
        return lmbda_x, lmbda_x_chunks
    
    def store_calculated_lmbda_chunk_post_processing(self, lmbda, lmbda_val):
        lmbda_x        = lmbda[0]
        lmbda_x_chunks = lmbda[1]
        lmbda_x_val    = lmbda_val
        
        lmbda_x_chunks.append(lmbda_x_val)
        
        return lmbda_x, lmbda_x_chunks
    
    def calculate_u_func(self, lmbda):
        lmbda_x        = lmbda[0]
        lmbda_x_chunks = lmbda[1]

        u_x        = [lmbda_x_val-1 for lmbda_x_val in lmbda_x]
        u_x_chunks = [lmbda_x_chunks_val-1 for lmbda_x_chunks_val in lmbda_x_chunks]

        return u_x, u_x_chunks
    
    def save_deformation_attributes(self, lmbda, u):
        lmbda_x        = lmbda[0]
        lmbda_x_chunks = lmbda[1]

        u_x        = u[0]
        u_x_chunks = u[1]

        self.lmbda_x        = lmbda_x
        self.lmbda_x_chunks = lmbda_x_chunks
        self.u_x            = u_x
        self.u_x_chunks     = u_x_chunks

    def set_post_processing(self):
        """
        Set up post-processing files and arrays
        """
        ppp = self.parameters["post_processing"]

        self.file_results = XDMFFile(MPI.comm_world, self.savedir+ppp["file_results"])
        self.file_results.parameters["rewrite_function_mesh"] = ppp["rewrite_function_mesh"]
        self.file_results.parameters["flush_output"]          = ppp["flush_output"]
        self.file_results.parameters["functions_share_mesh"]  = ppp["functions_share_mesh"]

        if ppp["save_lmbda_c_chunks"]:
            self.lmbda_c_chunks     = []
            self.lmbda_c_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_lmbda_c_eq_chunks"]:
            self.lmbda_c_eq_chunks     = []
            self.lmbda_c_eq_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_lmbda_nu_chunks"]:
            self.lmbda_nu_chunks     = []
            self.lmbda_nu_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_lmbda_c_tilde_chunks"]:
            self.lmbda_c_tilde_chunks     = []
            self.lmbda_c_tilde_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_lmbda_c_eq_tilde_chunks"]:
            self.lmbda_c_eq_tilde_chunks     = []
            self.lmbda_c_eq_tilde_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_lmbda_nu_tilde_chunks"]:
            self.lmbda_nu_tilde_chunks = []
            self.lmbda_nu_tilde_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_lmbda_c_tilde_max_chunks"]:
            self.lmbda_c_tilde_max_chunks     = []
            self.lmbda_c_tilde_max_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_lmbda_c_eq_tilde_max_chunks"]:
            self.lmbda_c_eq_tilde_max_chunks     = []
            self.lmbda_c_eq_tilde_max_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_lmbda_nu_tilde_max_chunks"]:
            self.lmbda_nu_tilde_max_chunks     = []
            self.lmbda_nu_tilde_max_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_upsilon_c_chunks"]:
            self.upsilon_c_chunks = []
            self.upsilon_c_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_Upsilon_c_chunks"]:
            self.Upsilon_c_chunks     = []
            self.Upsilon_c_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_d_c_chunks"]:
            self.d_c_chunks = []
            self.d_c_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_D_c_chunks"]:
            self.D_c_chunks     = []
            self.D_c_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_epsilon_cnu_diss_hat_chunks"]:
            self.epsilon_cnu_diss_hat_chunks     = []
            self.epsilon_cnu_diss_hat_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_Epsilon_cnu_diss_hat_chunks"]:
            self.Epsilon_cnu_diss_hat_chunks     = []
            self.Epsilon_cnu_diss_hat_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_epsilon_c_diss_hat_chunks"]:
            self.epsilon_c_diss_hat_chunks     = []
            self.epsilon_c_diss_hat_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_Epsilon_c_diss_hat_chunks"]:
            self.Epsilon_c_diss_hat_chunks     = []
            self.Epsilon_c_diss_hat_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_overline_epsilon_cnu_diss_hat_chunks"]:
            self.overline_epsilon_cnu_diss_hat_chunks     = []
            self.overline_epsilon_cnu_diss_hat_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_overline_Epsilon_cnu_diss_hat_chunks"]:
            self.overline_Epsilon_cnu_diss_hat_chunks     = []
            self.overline_Epsilon_cnu_diss_hat_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_overline_epsilon_c_diss_hat_chunks"]:
            self.overline_epsilon_c_diss_hat_chunks     = []
            self.overline_epsilon_c_diss_hat_chunks_val = [[0. for nu_chunk_indx in range(self.nu_chunks_num)] for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_overline_Epsilon_c_diss_hat_chunks"]:
            self.overline_Epsilon_c_diss_hat_chunks     = []
            self.overline_Epsilon_c_diss_hat_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        
        if ppp["save_u_chunks"]:
            self.set_u_chunks()
        
        if ppp["save_F_chunks"]:
            self.set_F_chunks()
        
        if ppp["save_sigma_chunks"]:
            self.set_sigma_chunks()
    
    def set_u_chunks(self):
        self.u_1_chunks = []
        self.u_1_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        self.u_2_chunks = []
        self.u_2_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
    
    def set_F_chunks(self):
        self.F_11_chunks = []
        self.F_11_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
    
    def set_sigma_chunks(self):
        self.sigma_11_chunks     = []
        self.sigma_11_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        self.sigma_11_penalty_term_chunks     = []
        self.sigma_11_penalty_term_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
        self.sigma_11_less_penalty_term_chunks     = []
        self.sigma_11_less_penalty_term_chunks_val = [0. for meshpoint_indx in range(self.meshpoint_num)]
    
    def solver_setup(self):
        """
        Setup the weak form solver
        """
        femp = self.parameters["fem"]

        if femp["solver_algorithm"] == "alternate_minimization":
            self.setup_u_solver()
            if femp["solver_bounded"]:
                self.setup_bounded_lmbda_c_tilde_solver()
            else:
                self.setup_unbounded_lmbda_c_tilde_solver()
        
        elif femp["solver_algorithm"] == "monolithic":
            if femp["solver_bounded"]:
                self.setup_bounded_monolithic_solver()
            else:
                self.setup_unbounded_monolithic_solver()

    def setup_u_solver(self):
        """
        Setup the displacement solver
        """
        self.problem_u = NonlinearVariationalProblem(self.WF_u, self.u, self.bc_u, J=self.Jac_u)
        self.solver_u = NonlinearVariationalSolver(self.problem_u)

        self.solver_u.parameters.update(self.solver_u_parameters_dict)
        info(self.solver_u.parameters, True)
    
    def setup_bounded_lmbda_c_tilde_solver(self):
        """
        Setup the bounded non-local chain stretch solver
        """
        self.problem_bounded_lmbda_c_tilde = NonlinearVariationalProblem(self.WF_lmbda_c_tilde, self.lmbda_c_tilde, self.bc_lmbda_c_tilde, J=self.Jac_lmbda_c_tilde)
        self.problem_bounded_lmbda_c_tilde.set_bounds(self.lmbda_c_tilde_lb.vector(), self.lmbda_c_tilde_ub.vector())

        self.solver_bounded_lmbda_c_tilde = NonlinearVariationalSolver(self.problem_bounded_lmbda_c_tilde)

        self.solver_bounded_lmbda_c_tilde.parameters.update(self.solver_bounded_lmbda_c_tilde_parameters_dict)
        info(self.solver_bounded_lmbda_c_tilde.parameters, True)
    
    def setup_unbounded_lmbda_c_tilde_solver(self):
        """
        Setup the unbounded non-local chain stretch solver
        """
        self.problem_unbounded_lmbda_c_tilde = NonlinearVariationalProblem(self.WF_lmbda_c_tilde, self.lmbda_c_tilde, self.bc_lmbda_c_tilde, J=self.Jac_lmbda_c_tilde)
        self.solver_unbounded_lmbda_c_tilde = NonlinearVariationalSolver(self.problem_unbounded_lmbda_c_tilde)

        self.solver_unbounded_lmbda_c_tilde.parameters.update(self.solver_unbounded_lmbda_c_tilde_parameters_dict)
        info(self.solver_unbounded_lmbda_c_tilde.parameters, True)
    
    def setup_bounded_monolithic_solver(self):
        """
        Setup the bounded monolithic weak form solver
        """
        error_message = """\
            The implementation of the bounded monolithic solver has not \
            been finalized yet. For now, only the unbounded monolithic \
            solver, the bounded alternate minimization solver, and the \
            unbounded alternate minimization solver are permitted.
            """
        sys.exit(error_message)
    
    def setup_unbounded_monolithic_solver(self):
        """
        Setup the unbounded monolithic weak form solver
        """
        self.problem_unbounded_monolithic = NonlinearVariationalProblem(self.WF, self.mixed_space, self.bc_monolithic, J=self.Jac)
        self.solver_unbounded_monolithic = NonlinearVariationalSolver(self.problem_unbounded_monolithic)

        self.solver_unbounded_monolithic.parameters.update(self.solver_unbounded_monolithic_parameters_dict)
        info(self.solver_unbounded_monolithic.parameters, True)

        (self.u, self.lmbda_c_tilde) = self.mixed_space.split()
    
    def solve(self):
        """
        Solve the evolution problem via solving the weak form through
        the applied deformation evolution
        """
        # Time stepping
        for t_indx, t_val in enumerate(self.t):
            # Update time stepping
            self.t_indx = t_indx
            self.t_val = t_val
            print0("\033[1;32m--- Time step # {0:2d}: t = {1:.3f} for the weak form network deformation ---\033[1;m".format(t_indx, t_val))
            self.set_loading()

            # Solve and account for network irreversibility
            self.solve_step()
            
            # Force all parallelization to unify after the solution step
            # and before post-processing
            MPI.barrier(MPI.comm_world)

            # Post-processing
            if self.t_indx in self.chunk_indx:
                self.post_processing()

            # Force all parallelization to unify after post-processing
            # and before user-defined post-processing
            MPI.barrier(MPI.comm_world)

            self.user_post_processing()
        
        # Force all parallelization to unify after user-defined
        # post-processing and before finalization
        MPI.barrier(MPI.comm_world)

        # Save chunks
        self.save_chunks()
    
    def set_loading(self):
        """
        Update Dirichlet boundary conditions
        """
        pass
    
    def solve_step(self):
        """
        Solve the weak form
        """
        femp = self.parameters["fem"]

        if femp["solver_algorithm"] == "alternate_minimization":
            if femp["solver_bounded"]:
                self.solve_bounded_alternate_minimization()
            else:
                self.solve_unbounded_alternate_minimization()
        
        elif femp["solver_algorithm"] == "monolithic":
            if femp["solver_bounded"]:
                self.solve_bounded_monolithic()
            else:
                self.solve_unbounded_monolithic()
        
        # update maximal non-local chain stretch to account for network
        # irreversibility
        self.lmbda_c_tilde_max = project(conditional(gt(self.lmbda_c_tilde, self.lmbda_c_tilde_max), self.lmbda_c_tilde, self.lmbda_c_tilde_max), self.V_lmbda_c_tilde)
        # update the gradient activity to account for the decreasing
        # non-local interaction for increasing non-local damage
        self.g = self.g_ufl_fenics_mesh_func()
        # update the normalized anisotropic interaction tensor to
        # account for the shape, size, and orientation of non-local
        # interactions at the microscale of the deformed polymer network
        self.H_tilde = self.H_tilde_ufl_fenics_mesh_func()
    
    def solve_bounded_alternate_minimization(self):
        """
        Solve the bounded alternate minimization problem
        """
        dp = self.parameters["deformation"]

        itrtn = 1
        error_lmbda_c_tilde = 1.

        while itrtn < dp["itrtn_max_lmbda_c_tilde_val"] and error_lmbda_c_tilde > dp["tol_lmbda_c_tilde_val"]:
            error_lmbda_c_tilde = 0.
            # solve for the displacement while holding non-local chain stretch fixed
            self.solve_u()
            # solve for the non-local chain stretch while holding displacement fixed
            self.solve_bounded_lmbda_c_tilde()
            # calculate the L-infinity error norm for the non-local chain stretch
            lmbda_c_tilde_diff = self.lmbda_c_tilde.vector() - self.lmbda_c_tilde_prior.vector()
            error_lmbda_c_tilde = lmbda_c_tilde_diff.norm('linf')
            # monitor the results
            print0("Bounded alternate minimization scheme: Iteration # {0:3d}; error = {1:>14.8f}".format(itrtn, error_lmbda_c_tilde))
            # update prior non-local chain stretch
            self.lmbda_c_tilde_prior.assign(self.lmbda_c_tilde)
            # update iteration
            itrtn += 1
    
    def solve_unbounded_alternate_minimization(self):
        """
        Solve the unbounded alternate minimization problem
        """
        dp = self.parameters["deformation"]

        itrtn = 1
        error_lmbda_c_tilde = 1.

        while itrtn < dp["itrtn_max_lmbda_c_tilde_val"] and error_lmbda_c_tilde > dp["tol_lmbda_c_tilde_val"]:
            error_lmbda_c_tilde = 0.
            # solve for the displacement while holding non-local chain stretch fixed
            self.solve_u()
            # solve for the non-local chain stretch while holding displacement fixed
            self.solve_unbounded_lmbda_c_tilde()
            # calculate the L-infinity error norm for the non-local chain stretch
            lmbda_c_tilde_diff = self.lmbda_c_tilde.vector() - self.lmbda_c_tilde_prior.vector()
            error_lmbda_c_tilde = lmbda_c_tilde_diff.norm('linf')
            # monitor the results
            print0("Unbounded alternate minimization scheme: Iteration # {0:3d}; error = {1:>14.8f}".format(itrtn, error_lmbda_c_tilde))
            # update prior non-local chain stretch
            self.lmbda_c_tilde_prior.assign(self.lmbda_c_tilde)
            # update iteration
            itrtn += 1
    
    def solve_bounded_monolithic(self):
        """
        Solve the bounded monolithic problem
        """
        error_message = """\
            The implementation of the bounded monolithic solver has not \
            been finalized yet. For now, only the unbounded monolithic \
            solver, the bounded alternate minimization solver, and the \
            unbounded alternate minimization solver are permitted.
            """
        sys.exit(error_message)
    
    def solve_unbounded_monolithic(self):
        """
        Solve the unbounded monolithic problem
        """
        print0("Displacement and non-local chain stretch unbounded monolithic problem")
        (iter, converged) = self.solver_unbounded_monolithic.solve()
    
    def solve_u(self):
        """
        Solve the displacement problem
        """
        print0("Displacement problem")
        (iter, converged) = self.solver_u.solve()
    
    def solve_bounded_lmbda_c_tilde(self):
        """
        Solve the bounded non-local chain stretch problem
        """
        print0("Non-local chain stretch problem")
        (iter, converged) = self.solver_bounded_lmbda_c_tilde.solve()
    
    def solve_unbounded_lmbda_c_tilde(self):
        """
        Solve the unbounded non-local chain stretch problem
        """
        print0("Non-local chain stretch problem")
        (iter, converged) = self.solver_unbounded_lmbda_c_tilde.solve()
    
    def post_processing(self):
        """
        Post-processing results
        """
        ppp  = self.parameters["post_processing"]

        if ppp["save_lmbda_c_mesh"]:
            local_project(self.lmbda_c, self.V_DG_scalar, self.V_lmbda_c)
            self.V_lmbda_c.rename("Chain stretch", "")
            self.file_results.write(self.V_lmbda_c, self.t_val)
        
        if ppp["save_lmbda_c_chunks"]:
            local_project(self.lmbda_c, self.V_DG_scalar, self.V_lmbda_c)
            for meshpoint_indx in range(self.meshpoint_num):
                MPI.barrier(MPI.comm_world)
                self.lmbda_c_chunks_val[meshpoint_indx] = peval(self.V_lmbda_c, self.meshpoints_list[meshpoint_indx])
            self.lmbda_c_chunks.append(deepcopy(self.lmbda_c_chunks_val))
        
        if ppp["save_lmbda_c_eq_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                lmbda_c_eq___nu_val = self.lmbda_c_eq_ufl_fenics_mesh_func(nu_indx)
                local_project(lmbda_c_eq___nu_val, self.V_DG_scalar, self.V_lmbda_c_eq)

                nu_str = str(self.nu_list[nu_indx])
                name_str = "Equilibrium chain stretch nu = " + nu_str

                self.V_lmbda_c_eq.rename(name_str, "")
                self.file_results.write(self.V_lmbda_c_eq, self.t_val)
        
        if ppp["save_lmbda_c_eq_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    lmbda_c_eq___nu_val = self.lmbda_c_eq_ufl_fenics_mesh_func(nu_indx)
                    local_project(lmbda_c_eq___nu_val, self.V_DG_scalar, self.V_lmbda_c_eq)
                    MPI.barrier(MPI.comm_world)
                    self.lmbda_c_eq_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_lmbda_c_eq, self.meshpoints_list[meshpoint_indx])
            self.lmbda_c_eq_chunks.append(deepcopy(self.lmbda_c_eq_chunks_val))
        
        if ppp["save_lmbda_nu_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                lmbda_nu___nu_val = self.lmbda_nu_ufl_fenics_mesh_func(nu_indx)
                local_project(lmbda_nu___nu_val, self.V_DG_scalar, self.V_lmbda_nu)

                nu_str = str(self.nu_list[nu_indx])
                name_str = "Segment stretch nu = " + nu_str

                self.V_lmbda_nu.rename(name_str, "")
                self.file_results.write(self.V_lmbda_nu, self.t_val)
        
        if ppp["save_lmbda_nu_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    lmbda_nu___nu_val = self.lmbda_nu_ufl_fenics_mesh_func(nu_indx)
                    local_project(lmbda_nu___nu_val, self.V_DG_scalar, self.V_lmbda_nu)
                    MPI.barrier(MPI.comm_world)
                    self.lmbda_nu_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_lmbda_nu, self.meshpoints_list[meshpoint_indx])
            self.lmbda_nu_chunks.append(deepcopy(self.lmbda_nu_chunks_val))
        
        if ppp["save_lmbda_c_tilde_mesh"]:
            self.lmbda_c_tilde.rename("Non-local chain stretch", "lmbda_c_tilde")
            self.file_results.write(self.lmbda_c_tilde, self.t_val)
        
        if ppp["save_lmbda_c_tilde_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                MPI.barrier(MPI.comm_world)
                self.lmbda_c_tilde_chunks_val[meshpoint_indx] = peval(self.lmbda_c_tilde, self.meshpoints_list[meshpoint_indx])
            self.lmbda_c_tilde_chunks.append(deepcopy(self.lmbda_c_tilde_chunks_val))
        
        if ppp["save_lmbda_c_eq_tilde_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                lmbda_c_eq_tilde___nu_val = self.lmbda_c_eq_tilde_ufl_fenics_mesh_func(nu_indx)
                local_project(lmbda_c_eq_tilde___nu_val, self.V_DG_scalar, self.V_lmbda_c_eq_tilde)

                nu_str = str(self.nu_list[nu_indx])
                name_str = "Non-local equilibrium chain stretch nu = " + nu_str

                self.V_lmbda_c_eq_tilde.rename(name_str, "")
                self.file_results.write(self.V_lmbda_c_eq_tilde, self.t_val)
        
        if ppp["save_lmbda_c_eq_tilde_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    lmbda_c_eq_tilde___nu_val = self.lmbda_c_eq_tilde_ufl_fenics_mesh_func(nu_indx)
                    local_project(lmbda_c_eq_tilde___nu_val, self.V_DG_scalar, self.V_lmbda_c_eq_tilde)
                    MPI.barrier(MPI.comm_world)
                    self.lmbda_c_eq_tilde_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_lmbda_c_eq_tilde, self.meshpoints_list[meshpoint_indx])
            self.lmbda_c_eq_tilde_chunks.append(deepcopy(self.lmbda_c_eq_tilde_chunks_val))
        
        if ppp["save_lmbda_nu_tilde_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                lmbda_nu_tilde___nu_val = self.lmbda_nu_tilde_ufl_fenics_mesh_func(nu_indx)
                local_project(lmbda_nu_tilde___nu_val, self.V_DG_scalar, self.V_lmbda_nu_tilde)

                nu_str = str(self.nu_list[nu_indx])
                name_str = "Non-local segment stretch nu = " + nu_str

                self.V_lmbda_nu_tilde.rename(name_str, "")
                self.file_results.write(self.V_lmbda_nu_tilde, self.t_val)
        
        if ppp["save_lmbda_nu_tilde_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    lmbda_nu_tilde___nu_val = self.lmbda_nu_tilde_ufl_fenics_mesh_func(nu_indx)
                    local_project(lmbda_nu_tilde___nu_val, self.V_DG_scalar, self.V_lmbda_nu_tilde)
                    MPI.barrier(MPI.comm_world)
                    self.lmbda_nu_tilde_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_lmbda_nu_tilde, self.meshpoints_list[meshpoint_indx])
            self.lmbda_nu_tilde_chunks.append(deepcopy(self.lmbda_nu_tilde_chunks_val))
        
        if ppp["save_lmbda_c_tilde_max_mesh"]:
            self.lmbda_c_tilde_max.rename("Maximal non-local chain stretch", "lmbda_c_tilde_max")
            self.file_results.write(self.lmbda_c_tilde_max, self.t_val)
        
        if ppp["save_lmbda_c_tilde_max_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                MPI.barrier(MPI.comm_world)
                self.lmbda_c_tilde_max_chunks_val[meshpoint_indx] = peval(self.lmbda_c_tilde_max, self.meshpoints_list[meshpoint_indx])
            self.lmbda_c_tilde_max_chunks.append(deepcopy(self.lmbda_c_tilde_max_chunks_val))
        
        if ppp["save_lmbda_c_eq_tilde_max_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                lmbda_c_eq_tilde_max___nu_val = self.lmbda_c_eq_tilde_max_ufl_fenics_mesh_func(nu_indx)
                local_project(lmbda_c_eq_tilde_max___nu_val, self.V_DG_scalar, self.V_lmbda_c_eq_tilde_max)

                nu_str = str(self.nu_list[nu_indx])
                name_str = "Maximal non-local equilibrium chain stretch nu = " + nu_str

                self.V_lmbda_c_eq_tilde_max.rename(name_str, "")
                self.file_results.write(self.V_lmbda_c_eq_tilde_max, self.t_val)
        
        if ppp["save_lmbda_c_eq_tilde_max_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    lmbda_c_eq_tilde_max___nu_val = self.lmbda_c_eq_tilde_max_ufl_fenics_mesh_func(nu_indx)
                    local_project(lmbda_c_eq_tilde_max___nu_val, self.V_DG_scalar, self.V_lmbda_c_eq_tilde_max)
                    MPI.barrier(MPI.comm_world)
                    self.lmbda_c_eq_tilde_max_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_lmbda_c_eq_tilde_max, self.meshpoints_list[meshpoint_indx])
            self.lmbda_c_eq_tilde_max_chunks.append(deepcopy(self.lmbda_c_eq_tilde_max_chunks_val))
        
        if ppp["save_lmbda_nu_tilde_max_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                lmbda_nu_tilde_max___nu_val = self.lmbda_nu_tilde_max_ufl_fenics_mesh_func(nu_indx)
                local_project(lmbda_nu_tilde_max___nu_val, self.V_DG_scalar, self.V_lmbda_nu_tilde_max)

                nu_str = str(self.nu_list[nu_indx])
                name_str = "Maximal non-local segment stretch nu = " + nu_str

                self.V_lmbda_nu_tilde_max.rename(name_str, "")
                self.file_results.write(self.V_lmbda_nu_tilde_max, self.t_val)
        
        if ppp["save_lmbda_nu_tilde_max_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    lmbda_nu_tilde_max___nu_val = self.lmbda_nu_tilde_max_ufl_fenics_mesh_func(nu_indx)
                    local_project(lmbda_nu_tilde_max___nu_val, self.V_DG_scalar, self.V_lmbda_nu_tilde_max)
                    MPI.barrier(MPI.comm_world)
                    self.lmbda_nu_tilde_max_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_lmbda_nu_tilde_max, self.meshpoints_list[meshpoint_indx])
            self.lmbda_nu_tilde_max_chunks.append(deepcopy(self.lmbda_nu_tilde_max_chunks_val))
        
        if ppp["save_upsilon_c_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                upsilon_c___nu_val = self.upsilon_c_ufl_fenics_mesh_func(nu_indx)
                local_project(upsilon_c___nu_val, self.V_DG_scalar, self.V_upsilon_c)

                nu_str = str(self.nu_list[nu_indx])
                name_str  = "Chain survival nu = " + nu_str

                self.V_upsilon_c.rename(name_str, "")
                self.file_results.write(self.V_upsilon_c, self.t_val)
        
        if ppp["save_upsilon_c_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    upsilon_c___nu_val = self.upsilon_c_ufl_fenics_mesh_func(nu_indx)
                    local_project(upsilon_c___nu_val, self.V_DG_scalar, self.V_upsilon_c)
                    MPI.barrier(MPI.comm_world)
                    self.upsilon_c_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_upsilon_c, self.meshpoints_list[meshpoint_indx])
            self.upsilon_c_chunks.append(deepcopy(self.upsilon_c_chunks_val))
        
        if ppp["save_Upsilon_c_mesh"]:
            Upsilon_c_val = self.Upsilon_c_ufl_fenics_mesh_func()
            local_project(Upsilon_c_val, self.V_DG_scalar, self.V_Upsilon_c)
            self.V_Upsilon_c.rename("Average chain survival", "")
            self.file_results.write(self.V_Upsilon_c, self.t_val)
        
        if ppp["save_Upsilon_c_chunks"]:
            Upsilon_c_val = self.Upsilon_c_ufl_fenics_mesh_func()
            local_project(Upsilon_c_val, self.V_DG_scalar, self.V_Upsilon_c)
            for meshpoint_indx in range(self.meshpoint_num):
                MPI.barrier(MPI.comm_world)
                self.Upsilon_c_chunks_val[meshpoint_indx] = peval(self.V_Upsilon_c, self.meshpoints_list[meshpoint_indx])
            self.Upsilon_c_chunks.append(deepcopy(self.Upsilon_c_chunks_val))
        
        if ppp["save_d_c_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                d_c___nu_val = self.d_c_ufl_fenics_mesh_func(nu_indx)
                local_project(d_c___nu_val, self.V_DG_scalar, self.V_d_c)

                nu_str = str(self.nu_list[nu_indx])
                name_str  = "Chain damage nu = " + nu_str

                self.V_d_c.rename(name_str, "")
                self.file_results.write(self.V_d_c, self.t_val)
        
        if ppp["save_d_c_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    d_c___nu_val = self.d_c_ufl_fenics_mesh_func(nu_indx)
                    local_project(d_c___nu_val, self.V_DG_scalar, self.V_d_c)
                    MPI.barrier(MPI.comm_world)
                    self.d_c_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_d_c, self.meshpoints_list[meshpoint_indx])
            self.d_c_chunks.append(deepcopy(self.d_c_chunks_val))
        
        if ppp["save_D_c_mesh"]:
            D_c_val = self.D_c_ufl_fenics_mesh_func()
            local_project(D_c_val, self.V_DG_scalar, self.V_D_c)
            self.V_D_c.rename("Average chain damage", "")
            self.file_results.write(self.V_D_c, self.t_val)
        
        if ppp["save_D_c_chunks"]:
            D_c_val = self.D_c_ufl_fenics_mesh_func()
            local_project(D_c_val, self.V_DG_scalar, self.V_D_c)
            for meshpoint_indx in range(self.meshpoint_num):
                MPI.barrier(MPI.comm_world)
                self.D_c_chunks_val[meshpoint_indx] = peval(self.V_D_c, self.meshpoints_list[meshpoint_indx])
            self.D_c_chunks.append(deepcopy(self.D_c_chunks_val))
        
        if ppp["save_epsilon_cnu_diss_hat_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                epsilon_cnu_diss_hat___nu_val = self.epsilon_cnu_diss_hat_ufl_fenics_mesh_func(nu_indx)
                local_project(epsilon_cnu_diss_hat___nu_val, self.V_DG_scalar, self.V_epsilon_cnu_diss_hat)

                nu_str = str(self.nu_list[nu_indx])
                name_str = "Per segment nondimensional dissipated chain scission energy nu = " + nu_str

                self.V_epsilon_cnu_diss_hat.rename(name_str, "")
                self.file_results.write(self.V_epsilon_cnu_diss_hat, self.t_val)
        
        if ppp["save_epsilon_cnu_diss_hat_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    epsilon_cnu_diss_hat___nu_val = self.epsilon_cnu_diss_hat_ufl_fenics_mesh_func(nu_indx)
                    local_project(epsilon_cnu_diss_hat___nu_val, self.V_DG_scalar, self.V_epsilon_cnu_diss_hat)
                    MPI.barrier(MPI.comm_world)
                    self.epsilon_cnu_diss_hat_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_epsilon_cnu_diss_hat, self.meshpoints_list[meshpoint_indx])
            self.epsilon_cnu_diss_hat_chunks.append(deepcopy(self.epsilon_cnu_diss_hat_chunks_val))
        
        if ppp["save_Epsilon_cnu_diss_hat_mesh"]:
            Epsilon_cnu_diss_hat_val = self.Epsilon_cnu_diss_hat_ufl_fenics_mesh_func()
            local_project(Epsilon_cnu_diss_hat_val, self.V_DG_scalar, self.V_Epsilon_cnu_diss_hat)
            self.V_Epsilon_cnu_diss_hat.rename("Average per segment nondimensional dissipated chain scission energy", "")
            self.file_results.write(self.V_Epsilon_cnu_diss_hat, self.t_val)
        
        if ppp["save_Epsilon_cnu_diss_hat_chunks"]:
            Epsilon_cnu_diss_hat_val = self.Epsilon_cnu_diss_hat_ufl_fenics_mesh_func()
            local_project(Epsilon_cnu_diss_hat_val, self.V_DG_scalar, self.V_Epsilon_cnu_diss_hat)
            for meshpoint_indx in range(self.meshpoint_num):
                MPI.barrier(MPI.comm_world)
                self.Epsilon_cnu_diss_hat_chunks_val[meshpoint_indx] = peval(self.V_Epsilon_cnu_diss_hat, self.meshpoints_list[meshpoint_indx])
            self.Epsilon_cnu_diss_hat_chunks.append(deepcopy(self.Epsilon_cnu_diss_hat_chunks_val))
        
        if ppp["save_epsilon_c_diss_hat_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                epsilon_c_diss_hat___nu_val = self.epsilon_c_diss_hat_ufl_fenics_mesh_func(nu_indx)
                local_project(epsilon_c_diss_hat___nu_val, self.V_DG_scalar, self.V_epsilon_c_diss_hat)

                nu_str = str(self.nu_list[nu_indx])
                name_str = "Nondimensional dissipated chain scission energy nu = " + nu_str

                self.V_epsilon_c_diss_hat.rename(name_str, "")
                self.file_results.write(self.V_epsilon_c_diss_hat, self.t_val)
        
        if ppp["save_epsilon_c_diss_hat_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    epsilon_c_diss_hat___nu_val = self.epsilon_c_diss_hat_ufl_fenics_mesh_func(nu_indx)
                    local_project(epsilon_c_diss_hat___nu_val, self.V_DG_scalar, self.V_epsilon_c_diss_hat)
                    MPI.barrier(MPI.comm_world)
                    self.epsilon_c_diss_hat_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_epsilon_c_diss_hat, self.meshpoints_list[meshpoint_indx])
            self.epsilon_c_diss_hat_chunks.append(deepcopy(self.epsilon_c_diss_hat_chunks_val))
        
        if ppp["save_Epsilon_c_diss_hat_mesh"]:
            Epsilon_c_diss_hat_val = self.Epsilon_c_diss_hat_ufl_fenics_mesh_func()
            local_project(Epsilon_c_diss_hat_val, self.V_DG_scalar, self.V_Epsilon_c_diss_hat)
            self.V_Epsilon_c_diss_hat.rename("Average nondimensional dissipated chain scission energy", "")
            self.file_results.write(self.V_Epsilon_c_diss_hat, self.t_val)
        
        if ppp["save_Epsilon_c_diss_hat_chunks"]:
            Epsilon_c_diss_hat_val = self.Epsilon_c_diss_hat_ufl_fenics_mesh_func()
            local_project(Epsilon_c_diss_hat_val, self.V_DG_scalar, self.V_Epsilon_c_diss_hat)
            for meshpoint_indx in range(self.meshpoint_num):
                MPI.barrier(MPI.comm_world)
                self.Epsilon_c_diss_hat_chunks_val[meshpoint_indx] = peval(self.V_Epsilon_c_diss_hat, self.meshpoints_list[meshpoint_indx])
            self.Epsilon_c_diss_hat_chunks.append(deepcopy(self.Epsilon_c_diss_hat_chunks_val))
        
        if ppp["save_overline_epsilon_cnu_diss_hat_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                overline_epsilon_cnu_diss_hat___nu_val = self.overline_epsilon_cnu_diss_hat_ufl_fenics_mesh_func(nu_indx)
                local_project(overline_epsilon_cnu_diss_hat___nu_val, self.V_DG_scalar, self.V_overline_epsilon_cnu_diss_hat)

                nu_str = str(self.nu_list[nu_indx])
                name_str = "Per segment nondimensional scaled dissipated chain scission energy nu = " + nu_str

                self.V_overline_epsilon_cnu_diss_hat.rename(name_str, "")
                self.file_results.write(self.V_overline_epsilon_cnu_diss_hat, self.t_val)
        
        if ppp["save_overline_epsilon_cnu_diss_hat_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    overline_epsilon_cnu_diss_hat___nu_val = self.overline_epsilon_cnu_diss_hat_ufl_fenics_mesh_func(nu_indx)
                    local_project(overline_epsilon_cnu_diss_hat___nu_val, self.V_DG_scalar, self.V_overline_epsilon_cnu_diss_hat)
                    MPI.barrier(MPI.comm_world)
                    self.overline_epsilon_cnu_diss_hat_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_overline_epsilon_cnu_diss_hat, self.meshpoints_list[meshpoint_indx])
            self.overline_epsilon_cnu_diss_hat_chunks.append(deepcopy(self.overline_epsilon_cnu_diss_hat_chunks_val))
        
        if ppp["save_overline_Epsilon_cnu_diss_hat_mesh"]:
            overline_Epsilon_cnu_diss_hat_val = self.overline_Epsilon_cnu_diss_hat_ufl_fenics_mesh_func()
            local_project(overline_Epsilon_cnu_diss_hat_val, self.V_DG_scalar, self.V_overline_Epsilon_cnu_diss_hat)
            self.V_overline_Epsilon_cnu_diss_hat.rename("Average per segment nondimensional scaled dissipated chain scission energy", "")
            self.file_results.write(self.V_overline_Epsilon_cnu_diss_hat, self.t_val)
        
        if ppp["save_overline_Epsilon_cnu_diss_hat_chunks"]:
            overline_Epsilon_cnu_diss_hat_val = self.overline_Epsilon_cnu_diss_hat_ufl_fenics_mesh_func()
            local_project(overline_Epsilon_cnu_diss_hat_val, self.V_DG_scalar, self.V_overline_Epsilon_cnu_diss_hat)
            for meshpoint_indx in range(self.meshpoint_num):
                MPI.barrier(MPI.comm_world)
                self.overline_Epsilon_cnu_diss_hat_chunks_val[meshpoint_indx] = peval(self.V_overline_Epsilon_cnu_diss_hat, self.meshpoints_list[meshpoint_indx])
            self.overline_Epsilon_cnu_diss_hat_chunks.append(deepcopy(self.overline_Epsilon_cnu_diss_hat_chunks_val))
        
        if ppp["save_overline_epsilon_c_diss_hat_mesh"]:
            for nu_chunk_indx in range(self.nu_chunks_num):
                nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                overline_epsilon_c_diss_hat___nu_val = self.overline_epsilon_c_diss_hat_ufl_fenics_mesh_func(nu_indx)
                local_project(overline_epsilon_c_diss_hat___nu_val, self.V_DG_scalar, self.V_overline_epsilon_c_diss_hat)

                nu_str = str(self.nu_list[nu_indx])
                name_str = "Nondimensional scaled dissipated chain scission energy nu = " + nu_str

                self.V_overline_epsilon_c_diss_hat.rename(name_str, "")
                self.file_results.write(self.V_overline_epsilon_c_diss_hat, self.t_val)
        
        if ppp["save_overline_epsilon_c_diss_hat_chunks"]:
            for meshpoint_indx in range(self.meshpoint_num):
                for nu_chunk_indx in range(self.nu_chunks_num):
                    nu_indx = self.nu_chunks_indx_in_nu_list[nu_chunk_indx]
                    overline_epsilon_c_diss_hat___nu_val = self.overline_epsilon_c_diss_hat_ufl_fenics_mesh_func(nu_indx)
                    local_project(overline_epsilon_c_diss_hat___nu_val, self.V_DG_scalar, self.V_overline_epsilon_c_diss_hat)
                    MPI.barrier(MPI.comm_world)
                    self.overline_epsilon_c_diss_hat_chunks_val[meshpoint_indx][nu_chunk_indx] = peval(self.V_overline_epsilon_c_diss_hat, self.meshpoints_list[meshpoint_indx])
            self.overline_epsilon_c_diss_hat_chunks.append(deepcopy(self.overline_epsilon_c_diss_hat_chunks_val))
        
        if ppp["save_overline_Epsilon_c_diss_hat_mesh"]:
            overline_Epsilon_c_diss_hat_val = self.overline_Epsilon_c_diss_hat_ufl_fenics_mesh_func()
            local_project(overline_Epsilon_c_diss_hat_val, self.V_DG_scalar, self.V_overline_Epsilon_c_diss_hat)
            self.V_overline_Epsilon_c_diss_hat.rename("Average nondimensional scaled dissipated chain scission energy", "")
            self.file_results.write(self.V_overline_Epsilon_c_diss_hat, self.t_val)
        
        if ppp["save_overline_Epsilon_c_diss_hat_chunks"]:
            overline_Epsilon_c_diss_hat_val = self.overline_Epsilon_c_diss_hat_ufl_fenics_mesh_func()
            local_project(overline_Epsilon_c_diss_hat_val, self.V_DG_scalar, self.V_overline_Epsilon_c_diss_hat)
            for meshpoint_indx in range(self.meshpoint_num):
                MPI.barrier(MPI.comm_world)
                self.overline_Epsilon_c_diss_hat_chunks_val[meshpoint_indx] = peval(self.V_overline_Epsilon_c_diss_hat, self.meshpoints_list[meshpoint_indx])
            self.overline_Epsilon_c_diss_hat_chunks.append(deepcopy(self.overline_Epsilon_c_diss_hat_chunks_val))
        
        if ppp["save_u_mesh"]:
            self.u.rename("Displacement", "u")
            self.file_results.write(self.u, self.t_val)
        
        if ppp["save_u_chunks"]:
            # self.u_chunks_post_processing()
            error_message = """\
                Error: The implementation for u chunk postprocessing \
                has not been finalized yet.
                """
            sys.exit(error_message)
        
        if ppp["save_F_mesh"]:
            local_project(self.F, self.V_DG_tensor, self.V_F)
            self.V_F.rename("Deformation gradient", "")
            self.file_results.write(self.V_F, self.t_val)
        
        if ppp["save_F_chunks"]:
            # self.F_chunks_post_processing()
            error_message = """\
                Error: The implementation for F chunk postprocessing \
                has not been finalized yet.
                """
            sys.exit(error_message)

        if ppp["save_sigma_mesh"]:
            sigma_val = self.cauchy_stress_ufl_fenics_mesh_func()
            sigma_penalty_term_val = self.cauchy_stress_penalty_term_ufl_fenics_mesh_func()
            sigma_less_penalty_term_val = sigma_val - sigma_penalty_term_val

            local_project(sigma_val, self.V_DG_tensor, self.V_sigma)
            local_project(sigma_penalty_term_val, self.V_DG_tensor, self.V_sigma_penalty_term)
            local_project(sigma_less_penalty_term_val, self.V_DG_tensor, self.V_sigma_less_penalty_term)

            self.V_sigma.rename("Normalized Cauchy stress", "")
            self.V_sigma_penalty_term.rename("Normalized Cauchy stress penalty term", "")
            self.V_sigma_less_penalty_term.rename("Normalized Cauchy stress less penalty term", "sigma_less_penalty_term_val")

            self.file_results.write(self.V_sigma, self.t_val)
            self.file_results.write(self.V_sigma_penalty_term, self.t_val)
            self.file_results.write(self.V_sigma_less_penalty_term, self.t_val)
        
        if ppp["save_sigma_chunks"]:
            # self.sigma_chunks_post_processing()
            error_message = """\
                Error: The implementation for sigma chunk \
                postprocessing has not been finalized yet.
                """
            sys.exit(error_message)
    
    def u_chunks_post_processing(self):
        for meshpoint_indx in range(self.meshpoint_num):
            MPI.barrier(MPI.comm_world)
            u_chunks_val = peval(self.u, self.meshpoints_list[meshpoint_indx])
            self.u_1_chunks_val[meshpoint_indx] = u_chunks_val[self.two_dim_vector_indx_dict["1"]]
            self.u_2_chunks_val[meshpoint_indx] = u_chunks_val[self.two_dim_vector_indx_dict["2"]]
        self.u_1_chunks.append(deepcopy(self.u_1_chunks_val))
        self.u_2_chunks.append(deepcopy(self.u_2_chunks_val))

    def F_chunks_post_processing(self):
        F_val = project(self.F, self.V_DG_tensor)
        for meshpoint_indx in range(self.meshpoint_num):
            MPI.barrier(MPI.comm_world)
            F_chunks_val = peval(F_val, self.meshpoints_list[meshpoint_indx])
            self.F_11_chunks_val[meshpoint_indx] = F_chunks_val[self.two_dim_tensor2voigt_vector_indx_dict["11"]]
        self.F_11_chunks.append(deepcopy(self.F_11_chunks_val))
    
    def sigma_chunks_post_processing(self):
        sigma_val = self.cauchy_stress_ufl_fenics_mesh_func()
        sigma_penalty_term_val = self.cauchy_stress_penalty_term_ufl_fenics_mesh_func()
        sigma_less_penalty_term_val = sigma_val - sigma_penalty_term_val
        sigma_val = project(sigma_val, self.V_DG_tensor)
        sigma_penalty_term_val = project(sigma_penalty_term_val, self.V_DG_tensor)
        sigma_less_penalty_term_val = project(sigma_less_penalty_term_val, self.V_DG_tensor)
        for meshpoint_indx in range(self.meshpoint_num):
            MPI.barrier(MPI.comm_world)
            sigma_chunks_val = peval(sigma_val, self.meshpoints_list[meshpoint_indx])
            sigma_penalty_term_chunks_val = peval(sigma_penalty_term_val, self.meshpoints_list[meshpoint_indx])
            sigma_less_penalty_term_chunks_val = peval(sigma_less_penalty_term_val, self.meshpoints_list[meshpoint_indx])
            self.sigma_11_chunks_val[meshpoint_indx] = sigma_chunks_val[self.two_dim_tensor2voigt_vector_indx_dict["11"]]
            self.sigma_11_penalty_term_chunks_val[meshpoint_indx] = sigma_penalty_term_chunks_val[self.two_dim_tensor2voigt_vector_indx_dict["11"]]
            self.sigma_11_less_penalty_term_chunks_val[meshpoint_indx] = sigma_less_penalty_term_chunks_val[self.two_dim_tensor2voigt_vector_indx_dict["11"]]
        self.sigma_11_chunks.append(deepcopy(self.sigma_11_chunks_val))
        self.sigma_11_penalty_term_chunks.append(deepcopy(self.sigma_11_penalty_term_chunks_val))
        self.sigma_11_less_penalty_term_chunks.append(deepcopy(self.sigma_11_less_penalty_term_chunks_val))

    def user_post_processing(self):
        """
        User post-processing
        """
        pass

    def save_chunks(self):
        """
        Save chunks
        """
        pass

    def finalization(self):
        """
        Plot the chunked results from the evolution problem
        """
        pass
    
    def first_pk_stress_ufl_fenics_mesh_func(self):
        """
        Nondimensional first Piola-Kirchhoff stress tensor
        """
        network = self.material

        first_pk_stress_val = Constant(0.0)*self.I
        for nu_indx in range(self.nu_num):
            nu_val = network.nu_list[nu_indx]
            P_nu___nu_val = network.P_nu_list[nu_indx]
            A_nu___nu_val = network.A_nu_list[nu_indx]
            lmbda_c_eq___nu_val = self.lmbda_c*A_nu___nu_val
            lmbda_nu___nu_val = network.composite_ufjc_ufl_fenics_list[nu_indx].lmbda_nu_ufl_fenics_func(lmbda_c_eq___nu_val)
            xi_c___nu_val = network.composite_ufjc_ufl_fenics_list[nu_indx].xi_c_ufl_fenics_func(lmbda_nu___nu_val, lmbda_c_eq___nu_val)
            upsilon_c___nu_val = self.upsilon_c_ufl_fenics_mesh_func(nu_indx)
            first_pk_stress_val += upsilon_c___nu_val*P_nu___nu_val*nu_val*A_nu___nu_val*xi_c___nu_val/(3.*self.lmbda_c)*self.F
        first_pk_stress_val += self.first_pk_stress_penalty_term_ufl_fenics_mesh_func()
        return first_pk_stress_val
    
    def first_pk_stress_penalty_term_ufl_fenics_mesh_func(self):
        """
        Penalty term associated with near-incompressibility in the
        nondimensional first Piola-Kirchhoff stress tensor
        """
        dp = self.parameters["deformation"]
        return self.Upsilon_c_cubed_ufl_fenics_mesh_func()*dp["K__G"]*(self.J-1)*self.J*self.F_inv.T

    def cauchy_stress_ufl_fenics_mesh_func(self):
        """
        Nondimensional Cauchy stress tensor
        """
        return self.first_pk_stress_ufl_fenics_mesh_func()/self.J*self.F.T
    
    def cauchy_stress_penalty_term_ufl_fenics_mesh_func(self):
        """
        Penalty term associated with near-incompressibility in the
        nondimensional Cauchy stress tensor
        """
        return self.first_pk_stress_penalty_term_ufl_fenics_mesh_func()/self.J*self.F.T
    
    def lmbda_c_eq_tilde_ufl_fenics_mesh_func(self, nu_indx):
        """
        Non-local equilibrium chain stretch for chains with a particular
        segment number
        """
        network = self.material

        A_nu___nu_val = network.A_nu_list[nu_indx]
        lmbda_c_eq_tilde___nu_val = self.lmbda_c_tilde*A_nu___nu_val
        return lmbda_c_eq_tilde___nu_val
    
    def lmbda_nu_tilde_ufl_fenics_mesh_func(self, nu_indx):
        """
        Non-local segment stretch for chains with a particular segment
        number
        """
        network = self.material

        lmbda_c_eq_tilde___nu_val = self.lmbda_c_eq_tilde_ufl_fenics_mesh_func(nu_indx)
        lmbda_nu_tilde___nu_val = network.composite_ufjc_ufl_fenics_list[nu_indx].lmbda_nu_ufl_fenics_func(lmbda_c_eq_tilde___nu_val)
        return lmbda_nu_tilde___nu_val
    
    def lmbda_c_eq_tilde_max_ufl_fenics_mesh_func(self, nu_indx):
        """
        Maximum non-local equilibrium chain stretch for chains with a
        particular segment number
        """
        network = self.material

        A_nu___nu_val = network.A_nu_list[nu_indx]
        lmbda_c_eq_tilde_max___nu_val = self.lmbda_c_tilde_max*A_nu___nu_val
        return lmbda_c_eq_tilde_max___nu_val
    
    def lmbda_nu_tilde_max_ufl_fenics_mesh_func(self, nu_indx):
        """
        Maximum non-local segment stretch for chains with a particular
        segment number
        """
        network = self.material

        lmbda_c_eq_tilde_max___nu_val = self.lmbda_c_eq_tilde_max_ufl_fenics_mesh_func(nu_indx)
        lmbda_nu_tilde_max___nu_val = network.composite_ufjc_ufl_fenics_list[nu_indx].lmbda_nu_ufl_fenics_func(lmbda_c_eq_tilde_max___nu_val)
        return lmbda_nu_tilde_max___nu_val
    
    def upsilon_c_ufl_fenics_mesh_func(self, nu_indx):
        """
        Chain degradation for chains with a particular segment number
        """
        dp = self.parameters["deformation"]

        return (1.-dp["k_cond_val"])*(1.-self.d_c_ufl_fenics_mesh_func(nu_indx)) + dp["k_cond_val"]
    
    def d_c_ufl_fenics_mesh_func(self, nu_indx):
        """
        Chain damage for chains with a particular segment number
        """
        tau = Constant(2700)
        lmbda_nu_tilde_max_crit = Constant(1.003)
        lmbda_nu_tilde_max___nu_val = self.lmbda_nu_tilde_max_ufl_fenics_mesh_func(nu_indx)
        return 1. - sqrt(1.-1./(1.+exp(-tau*(lmbda_nu_tilde_max___nu_val-lmbda_nu_tilde_max_crit))))
    
    def Upsilon_c_ufl_fenics_mesh_func(self):
        """
        Average network chain degradation
        """
        network = self.material

        Upsilon_c_val = Constant(0.0)
        for nu_indx in range(self.nu_num):
            P_nu___nu_val = network.P_nu_list[nu_indx]
            upsilon_c___nu_val = self.upsilon_c_ufl_fenics_mesh_func(nu_indx)
            Upsilon_c_val += P_nu___nu_val*upsilon_c___nu_val
        Upsilon_c_val = Upsilon_c_val / network.P_nu_sum
        return Upsilon_c_val
    
    def Upsilon_c_squared_ufl_fenics_mesh_func(self):
        """
        Average network squared chain degradation
        """
        network = self.material

        Upsilon_c_val = Constant(0.0)
        for nu_indx in range(self.nu_num):
            P_nu___nu_val = network.P_nu_list[nu_indx]
            upsilon_c___nu_val = self.upsilon_c_ufl_fenics_mesh_func(nu_indx)
            Upsilon_c_val += P_nu___nu_val*upsilon_c___nu_val**2
        Upsilon_c_val = Upsilon_c_val / network.P_nu_sum
        return Upsilon_c_val
    
    def Upsilon_c_cubed_ufl_fenics_mesh_func(self):
        """
        Average network cubed chain degradation
        """
        network = self.material

        Upsilon_c_val = Constant(0.0)
        for nu_indx in range(self.nu_num):
            P_nu___nu_val = network.P_nu_list[nu_indx]
            upsilon_c___nu_val = self.upsilon_c_ufl_fenics_mesh_func(nu_indx)
            Upsilon_c_val += P_nu___nu_val*upsilon_c___nu_val**3
        Upsilon_c_val = Upsilon_c_val / network.P_nu_sum
        return Upsilon_c_val
    
    def D_c_ufl_fenics_mesh_func(self):
        """
        Average network chain damage
        """
        network = self.material

        D_c_val = Constant(0.0)
        for nu_indx in range(self.nu_num):
            P_nu___nu_val = network.P_nu_list[nu_indx]
            d_c___nu_val = self.d_c_ufl_fenics_mesh_func(nu_indx)
            D_c_val += P_nu___nu_val*d_c___nu_val
        D_c_val = D_c_val / network.P_nu_sum
        return D_c_val
    
    def D_c_squared_ufl_fenics_mesh_func(self):
        """
        Average network squared chain damage
        """
        network = self.material

        D_c_val = Constant(0.0)
        for nu_indx in range(self.nu_num):
            P_nu___nu_val = network.P_nu_list[nu_indx]
            d_c___nu_val = self.d_c_ufl_fenics_mesh_func(nu_indx)
            D_c_val += P_nu___nu_val*d_c___nu_val**2
        D_c_val = D_c_val / network.P_nu_sum
        return D_c_val
    
    def D_c_cubed_ufl_fenics_mesh_func(self):
        """
        Average network cubed chain damage
        """
        network = self.material

        D_c_val = Constant(0.0)
        for nu_indx in range(self.nu_num):
            P_nu___nu_val = network.P_nu_list[nu_indx]
            d_c___nu_val = self.d_c_ufl_fenics_mesh_func(nu_indx)
            D_c_val += P_nu___nu_val*d_c___nu_val**3
        D_c_val = D_c_val / network.P_nu_sum
        return D_c_val
    
    def lmbda_c_eq_ufl_fenics_mesh_func(self, nu_indx):
        """
        Equilibrium chain stretch for chains with a particular segment
        number
        """
        network = self.material

        A_nu___nu_val = network.A_nu_list[nu_indx]
        lmbda_c_eq___nu_val = self.lmbda_c*A_nu___nu_val
        return lmbda_c_eq___nu_val
    
    def lmbda_nu_ufl_fenics_mesh_func(self, nu_indx):
        """
        Segment stretch for chains with a particular segment number
        """
        network = self.material

        lmbda_c_eq___nu_val = self.lmbda_c_eq_ufl_fenics_mesh_func(nu_indx)
        lmbda_nu___nu_val = network.composite_ufjc_ufl_fenics_list[nu_indx].lmbda_nu_ufl_fenics_func(lmbda_c_eq___nu_val)
        return lmbda_nu___nu_val
    
    def epsilon_cnu_diss_hat_ufl_fenics_mesh_func(self, nu_indx):
        """
        Nondimensional per segment dissipated chain scission energy for
        chains with a particular segment number
        """
        network = self.material

        lmbda_nu_tilde_max___nu_val = self.lmbda_nu_tilde_max_ufl_fenics_mesh_func(nu_indx)
        epsilon_cnu_diss_hat___nu_val = network.composite_ufjc_ufl_fenics_list[nu_indx].epsilon_cnu_diss_hat_equiv_ufl_fenics_func(lmbda_nu_tilde_max___nu_val)
        return epsilon_cnu_diss_hat___nu_val
    
    def epsilon_c_diss_hat_ufl_fenics_mesh_func(self, nu_indx):
        """
        Nondimensional dissipated chain scission energy for chains with
        a particular segment number
        """
        network = self.material

        nu_val = network.nu_list[nu_indx]
        epsilon_cnu_diss_hat___nu_val = self.epsilon_cnu_diss_hat_ufl_fenics_mesh_func(nu_indx)
        epsilon_c_diss_hat___nu_val = nu_val * epsilon_cnu_diss_hat___nu_val
        return epsilon_c_diss_hat___nu_val
    
    def overline_epsilon_cnu_diss_hat_ufl_fenics_mesh_func(self, nu_indx):
        """
        Nondimensional scaled per segment dissipated chain scission
        energy for chains with a particular segment number
        """
        network = self.material

        epsilon_cnu_diss_hat___nu_val = self.epsilon_cnu_diss_hat_ufl_fenics_mesh_func(nu_indx)
        overline_epsilon_cnu_diss_hat___nu_val = epsilon_cnu_diss_hat___nu_val / network.zeta_nu_char
        return overline_epsilon_cnu_diss_hat___nu_val
    
    def overline_epsilon_c_diss_hat_ufl_fenics_mesh_func(self, nu_indx):
        """
        Nondimensional scaled dissipated chain scission energy for
        chains with a particular segment number
        """
        network = self.material

        epsilon_c_diss_hat___nu_val = self.epsilon_c_diss_hat_ufl_fenics_mesh_func(nu_indx)
        overline_epsilon_c_diss_hat___nu_val = epsilon_c_diss_hat___nu_val / network.zeta_nu_char
        return overline_epsilon_c_diss_hat___nu_val
    
    def Epsilon_cnu_diss_hat_ufl_fenics_mesh_func(self):
        """
        Average network nondimensional per segment dissipated chain
        scission energy
        """
        network = self.material

        Epsilon_cnu_diss_hat_val = Constant(0.0)
        for nu_indx in range(self.nu_num):
            P_nu___nu_val = network.P_nu_list[nu_indx]
            epsilon_cnu_diss_hat___nu_val = self.epsilon_cnu_diss_hat_ufl_fenics_mesh_func(nu_indx)
            Epsilon_cnu_diss_hat_val += P_nu___nu_val*epsilon_cnu_diss_hat___nu_val
        Epsilon_cnu_diss_hat_val = Epsilon_cnu_diss_hat_val / network.P_nu_sum
        return Epsilon_cnu_diss_hat_val
    
    def Epsilon_c_diss_hat_ufl_fenics_mesh_func(self):
        """
        Average network nondimensional dissipated chain scission energy
        """
        network = self.material

        Epsilon_c_diss_hat_val = Constant(0.0)
        for nu_indx in range(self.nu_num):
            P_nu___nu_val = network.P_nu_list[nu_indx]
            epsilon_c_diss_hat___nu_val = self.epsilon_c_diss_hat_ufl_fenics_mesh_func(nu_indx)
            Epsilon_c_diss_hat_val += P_nu___nu_val*epsilon_c_diss_hat___nu_val
        Epsilon_c_diss_hat_val = Epsilon_c_diss_hat_val / network.P_nu_sum
        return Epsilon_c_diss_hat_val
    
    def overline_Epsilon_cnu_diss_hat_ufl_fenics_mesh_func(self):
        """
        Average network nondimensional scaled per segment dissipated chain
        scission energy
        """
        network = self.material

        overline_Epsilon_cnu_diss_hat_val = Constant(0.0)
        for nu_indx in range(self.nu_num):
            P_nu___nu_val = network.P_nu_list[nu_indx]
            overline_epsilon_cnu_diss_hat___nu_val = self.overline_epsilon_cnu_diss_hat_ufl_fenics_mesh_func(nu_indx)
            overline_Epsilon_cnu_diss_hat_val += P_nu___nu_val*overline_epsilon_cnu_diss_hat___nu_val
        overline_Epsilon_cnu_diss_hat_val = overline_Epsilon_cnu_diss_hat_val / network.P_nu_sum
        return overline_Epsilon_cnu_diss_hat_val
    
    def overline_Epsilon_c_diss_hat_ufl_fenics_mesh_func(self):
        """
        Average network nondimensional scaled dissipated chain scission
        energy
        """
        network = self.material

        overline_Epsilon_c_diss_hat_val = Constant(0.0)
        for nu_indx in range(self.nu_num):
            P_nu___nu_val = network.P_nu_list[nu_indx]
            overline_epsilon_c_diss_hat___nu_val = self.overline_epsilon_c_diss_hat_ufl_fenics_mesh_func(nu_indx)
            overline_Epsilon_c_diss_hat_val += P_nu___nu_val*overline_epsilon_c_diss_hat___nu_val
        overline_Epsilon_c_diss_hat_val = overline_Epsilon_c_diss_hat_val / network.P_nu_sum
        return overline_Epsilon_c_diss_hat_val
    
    def g_ufl_fenics_mesh_func(self):
        """
        Gradient activity
        """
        # dp = self.parameters["deformation"]

        # D_c_val = self.D_c_ufl_fenics_mesh_func()
        # g_val = 0.5 * (cos(DOLFIN_PI*D_c_val)+1.) * (1.-dp["k_cond_val"]) + dp["k_cond_val"]
        # return g_val
        return Constant(1.)
    
    def H_tilde_ufl_fenics_mesh_func(self):
        """
        Normalized anisotropic interaction tensor
        """
        # sigma_val = self.cauchy_stress_ufl_fenics_mesh_func()
        # I_sigma_val = tr(sigma_val)
        # III_sigma_val = det(sigma_val)

        # sigma_1_val = (I_sigma_val+sqrt(I_sigma_val**2-4.*III_sigma_val+DOLFIN_EPS)) / 2.
        # sigma_2_val = (I_sigma_val-sqrt(I_sigma_val**2-4.*III_sigma_val+DOLFIN_EPS)) / 2.

        # sigma_max_val = max_ufl_fenics_mesh_func(sigma_1_val, sigma_2_val)

        # Z_1_val_dnmntr = sigma_1_val - sigma_2_val
        # dolfin_eps_sgn = conditional(ge(Z_1_val_dnmntr, 0), DOLFIN_EPS, -1*DOLFIN_EPS)
        # Z_1_val_dnmntr = conditional(ge(abs(Z_1_val_dnmntr), DOLFIN_EPS), Z_1_val_dnmntr, dolfin_eps_sgn)
        # Z_1_val = 1. / Z_1_val_dnmntr * (sigma_val-sigma_2_val*self.I)

        # Z_2_val_dnmntr = sigma_2_val - sigma_1_val
        # dolfin_eps_sgn = conditional(ge(Z_2_val_dnmntr, 0), DOLFIN_EPS, -1*DOLFIN_EPS)
        # Z_2_val_dnmntr = conditional(ge(abs(Z_2_val_dnmntr), DOLFIN_EPS), Z_2_val_dnmntr, dolfin_eps_sgn)
        # Z_2_val = 1. / Z_2_val_dnmntr * (sigma_val-sigma_1_val*self.I)

        # H_tilde_val = (sigma_1_val/sigma_max_val)**2 * Z_1_val + (sigma_2_val/sigma_max_val)**2 * Z_2_val
        # H_tilde_val = conditional(ge(abs(Z_1_val_dnmntr), DOLFIN_EPS), H_tilde_val, self.I)
        # return H_tilde_val
        return self.I
