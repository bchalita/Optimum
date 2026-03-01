"""Seed data for the 15 canonical formulation templates."""

FORMULATION_TEMPLATES = [
    # 1. Vehicle Routing Problem (VRP)
    {
        "name": "Vehicle Routing Problem",
        "alias": "VRP",
        "category": "routing",
        "description": (
            "Determine optimal routes for a fleet of vehicles to serve a set of "
            "customers from a central depot. Each customer must be visited exactly once, "
            "and each vehicle must start and end at the depot. The objective is typically "
            "to minimize total travel distance or cost."
        ),
        "decision_variables": [
            {
                "name": "x_ijk",
                "description": "1 if vehicle k travels directly from node i to node j, 0 otherwise",
                "type": "binary",
            },
            {
                "name": "u_ik",
                "description": "Position of customer i in the route of vehicle k (used for subtour elimination)",
                "type": "integer",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize total travel distance across all vehicle routes",
            "expression": "sum over k in K, (i,j) in A: c_ij * x_ijk",
        },
        "constraints": [
            {
                "name": "visit_once",
                "description": "Each customer is visited exactly once by exactly one vehicle",
                "expression": "sum over k in K, j in V: x_ijk = 1, for all i in C",
            },
            {
                "name": "flow_conservation",
                "description": "If vehicle k arrives at a customer, it must also depart",
                "expression": "sum over i in V: x_ijk = sum over i in V: x_jik, for all j in C, k in K",
            },
            {
                "name": "depot_departure",
                "description": "Each vehicle departs from the depot at most once",
                "expression": "sum over j in C: x_0jk <= 1, for all k in K",
            },
            {
                "name": "depot_return",
                "description": "Each vehicle returns to the depot",
                "expression": "sum over i in C: x_i0k = sum over j in C: x_0jk, for all k in K",
            },
            {
                "name": "capacity",
                "description": "Total demand on each route does not exceed vehicle capacity",
                "expression": "sum over i in C: d_i * (sum over j in V: x_ijk) <= Q_k, for all k in K",
            },
            {
                "name": "subtour_elimination",
                "description": "Miller-Tucker-Zemlin subtour elimination constraints",
                "expression": "u_ik - u_jk + n * x_ijk <= n - 1, for all i,j in C, k in K",
            },
        ],
        "parameters": [
            {"name": "c_ij", "description": "Travel cost/distance from node i to node j", "type": "float"},
            {"name": "d_i", "description": "Demand of customer i", "type": "float"},
            {"name": "Q_k", "description": "Capacity of vehicle k", "type": "float"},
            {"name": "n", "description": "Number of customers", "type": "integer"},
            {"name": "K", "description": "Set of vehicles", "type": "set"},
            {"name": "C", "description": "Set of customers (excluding depot)", "type": "set"},
            {"name": "V", "description": "Set of all nodes (customers + depot)", "type": "set"},
            {"name": "A", "description": "Set of arcs (i,j) between nodes", "type": "set"},
        ],
        "tags": ["routing", "vehicle", "fleet", "delivery", "logistics", "capacitated", "TSP-variant"],
        "source": "Toth & Vigo (2014), Vehicle Routing: Problems, Methods, and Applications",
    },

    # 2. Travelling Salesman Problem (TSP)
    {
        "name": "Travelling Salesman Problem",
        "alias": "TSP",
        "category": "routing",
        "description": (
            "Find the shortest possible route that visits each city exactly once "
            "and returns to the starting city. A fundamental combinatorial optimization "
            "problem that appears in logistics, manufacturing, and circuit design."
        ),
        "decision_variables": [
            {
                "name": "x_ij",
                "description": "1 if the tour travels directly from city i to city j, 0 otherwise",
                "type": "binary",
            },
            {
                "name": "u_i",
                "description": "Position of city i in the tour sequence (MTZ formulation)",
                "type": "integer",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize total tour length (distance traveled)",
            "expression": "sum over (i,j) in A: c_ij * x_ij",
        },
        "constraints": [
            {
                "name": "depart_once",
                "description": "Each city is departed exactly once",
                "expression": "sum over j in V, j != i: x_ij = 1, for all i in V",
            },
            {
                "name": "arrive_once",
                "description": "Each city is arrived at exactly once",
                "expression": "sum over i in V, i != j: x_ij = 1, for all j in V",
            },
            {
                "name": "subtour_elimination",
                "description": "Miller-Tucker-Zemlin subtour elimination",
                "expression": "u_i - u_j + n * x_ij <= n - 1, for all i,j in V \\ {1}, i != j",
            },
        ],
        "parameters": [
            {"name": "c_ij", "description": "Distance or travel cost from city i to city j", "type": "float"},
            {"name": "n", "description": "Number of cities", "type": "integer"},
            {"name": "V", "description": "Set of all cities", "type": "set"},
            {"name": "A", "description": "Set of arcs (i,j) between cities", "type": "set"},
        ],
        "tags": ["routing", "tour", "salesman", "Hamiltonian", "circuit", "shortest"],
        "source": "Applegate, Bixby, Chvátal & Cook (2006), The Traveling Salesman Problem",
    },

    # 3. Facility Location Problem
    {
        "name": "Facility Location Problem",
        "alias": "FLP",
        "category": "assignment",
        "description": (
            "Decide which facilities to open from a set of candidate locations and "
            "how to assign customers to open facilities in order to minimize total "
            "fixed opening costs plus transportation costs. The uncapacitated variant "
            "places no limit on facility throughput."
        ),
        "decision_variables": [
            {
                "name": "y_j",
                "description": "1 if facility j is opened, 0 otherwise",
                "type": "binary",
            },
            {
                "name": "x_ij",
                "description": "Fraction of customer i's demand served by facility j (or binary assignment)",
                "type": "continuous",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize total fixed facility costs plus customer-to-facility transportation costs",
            "expression": "sum over j in F: f_j * y_j + sum over i in C, j in F: c_ij * d_i * x_ij",
        },
        "constraints": [
            {
                "name": "demand_satisfaction",
                "description": "Each customer's demand must be fully satisfied",
                "expression": "sum over j in F: x_ij = 1, for all i in C",
            },
            {
                "name": "facility_open",
                "description": "A customer can only be assigned to an open facility",
                "expression": "x_ij <= y_j, for all i in C, j in F",
            },
            {
                "name": "capacity",
                "description": "(Capacitated variant) Total demand assigned to facility j does not exceed its capacity",
                "expression": "sum over i in C: d_i * x_ij <= S_j * y_j, for all j in F",
            },
        ],
        "parameters": [
            {"name": "f_j", "description": "Fixed cost of opening facility j", "type": "float"},
            {"name": "c_ij", "description": "Unit transportation cost from facility j to customer i", "type": "float"},
            {"name": "d_i", "description": "Demand of customer i", "type": "float"},
            {"name": "S_j", "description": "Capacity of facility j (for capacitated variant)", "type": "float"},
            {"name": "F", "description": "Set of candidate facility locations", "type": "set"},
            {"name": "C", "description": "Set of customers", "type": "set"},
        ],
        "tags": ["facility", "location", "warehouse", "assignment", "fixed-cost", "capacitated"],
        "source": "Cornuejols, Nemhauser & Wolsey (1990); Daskin (2013), Network and Discrete Location",
    },

    # 4. Bin Packing Problem
    {
        "name": "Bin Packing Problem",
        "alias": "BPP",
        "category": "packing",
        "description": (
            "Pack a set of items with known sizes into the minimum number of "
            "fixed-capacity bins. Each item must be assigned to exactly one bin, "
            "and the total size of items in any bin cannot exceed its capacity."
        ),
        "decision_variables": [
            {
                "name": "y_j",
                "description": "1 if bin j is used, 0 otherwise",
                "type": "binary",
            },
            {
                "name": "x_ij",
                "description": "1 if item i is placed in bin j, 0 otherwise",
                "type": "binary",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize the total number of bins used",
            "expression": "sum over j in B: y_j",
        },
        "constraints": [
            {
                "name": "assignment",
                "description": "Each item must be assigned to exactly one bin",
                "expression": "sum over j in B: x_ij = 1, for all i in I",
            },
            {
                "name": "capacity",
                "description": "Total size of items in each bin cannot exceed bin capacity",
                "expression": "sum over i in I: s_i * x_ij <= C * y_j, for all j in B",
            },
        ],
        "parameters": [
            {"name": "s_i", "description": "Size (weight/volume) of item i", "type": "float"},
            {"name": "C", "description": "Capacity of each bin", "type": "float"},
            {"name": "I", "description": "Set of items to pack", "type": "set"},
            {"name": "B", "description": "Set of available bins (upper bound: one bin per item)", "type": "set"},
        ],
        "tags": ["packing", "bin", "container", "cutting-stock", "waste-minimization"],
        "source": "Martello & Toth (1990), Knapsack Problems",
    },

    # 5. 0-1 Knapsack Problem
    {
        "name": "0-1 Knapsack Problem",
        "alias": "KP",
        "category": "packing",
        "description": (
            "Select a subset of items, each with a value and a weight, to include "
            "in a knapsack of limited capacity so as to maximize total value without "
            "exceeding the weight limit. Each item is either fully included or excluded."
        ),
        "decision_variables": [
            {
                "name": "x_i",
                "description": "1 if item i is selected, 0 otherwise",
                "type": "binary",
            },
        ],
        "objective": {
            "type": "maximize",
            "description": "Maximize total value of selected items",
            "expression": "sum over i in I: v_i * x_i",
        },
        "constraints": [
            {
                "name": "capacity",
                "description": "Total weight of selected items cannot exceed knapsack capacity",
                "expression": "sum over i in I: w_i * x_i <= W",
            },
        ],
        "parameters": [
            {"name": "v_i", "description": "Value of item i", "type": "float"},
            {"name": "w_i", "description": "Weight of item i", "type": "float"},
            {"name": "W", "description": "Capacity of the knapsack", "type": "float"},
            {"name": "I", "description": "Set of items", "type": "set"},
        ],
        "tags": ["knapsack", "selection", "subset", "budget", "resource-allocation", "binary"],
        "source": "Martello & Toth (1990), Knapsack Problems; Kellerer, Pferschy & Pisinger (2004)",
    },

    # 6. Job Shop Scheduling
    {
        "name": "Job Shop Scheduling",
        "alias": "JSP",
        "category": "scheduling",
        "description": (
            "Schedule a set of jobs on a set of machines, where each job consists "
            "of a sequence of operations that must be processed in a specific order. "
            "Each machine can process at most one operation at a time. The objective "
            "is typically to minimize the makespan (total completion time)."
        ),
        "decision_variables": [
            {
                "name": "s_ij",
                "description": "Start time of operation j of job i",
                "type": "continuous",
            },
            {
                "name": "y_ijk_i2j2",
                "description": "1 if operation (i,j) is scheduled before operation (i2,j2) on the same machine, 0 otherwise",
                "type": "binary",
            },
            {
                "name": "C_max",
                "description": "Makespan (completion time of the last operation)",
                "type": "continuous",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize the makespan (time to complete all jobs)",
            "expression": "C_max",
        },
        "constraints": [
            {
                "name": "precedence",
                "description": "Each operation of a job cannot start until the previous operation of the same job is finished",
                "expression": "s_ij + p_ij <= s_i(j+1), for all operations j, j+1 in job i",
            },
            {
                "name": "no_overlap",
                "description": "Two operations on the same machine cannot overlap (disjunctive constraint)",
                "expression": "s_ij + p_ij <= s_i2j2 OR s_i2j2 + p_i2j2 <= s_ij, for operations (i,j), (i2,j2) on same machine",
            },
            {
                "name": "disjunctive_linearization",
                "description": "Big-M linearization of the no-overlap constraint",
                "expression": "s_ij + p_ij <= s_i2j2 + M * (1 - y_ijk_i2j2), and s_i2j2 + p_i2j2 <= s_ij + M * y_ijk_i2j2",
            },
            {
                "name": "makespan_definition",
                "description": "Makespan is at least as large as the completion time of every operation",
                "expression": "C_max >= s_ij + p_ij, for all i, j",
            },
            {
                "name": "non_negative_start",
                "description": "Start times are non-negative",
                "expression": "s_ij >= 0, for all i, j",
            },
        ],
        "parameters": [
            {"name": "p_ij", "description": "Processing time of operation j of job i", "type": "float"},
            {"name": "M", "description": "Big-M constant (sufficiently large number)", "type": "float"},
            {"name": "J", "description": "Set of jobs", "type": "set"},
            {"name": "M_set", "description": "Set of machines", "type": "set"},
            {"name": "O_i", "description": "Ordered set of operations for job i", "type": "set"},
            {"name": "mu_ij", "description": "Machine required by operation j of job i", "type": "integer"},
        ],
        "tags": ["scheduling", "job-shop", "makespan", "machines", "operations", "sequencing"],
        "source": "Pinedo (2016), Scheduling: Theory, Algorithms, and Systems",
    },

    # 7. Staff Scheduling / Shift Planning
    {
        "name": "Staff Scheduling / Shift Planning",
        "alias": "SSP",
        "category": "scheduling",
        "description": (
            "Assign employees to shifts over a planning horizon to meet staffing "
            "requirements while respecting labor regulations, employee preferences, "
            "and cost objectives. Covers nurse scheduling, workforce planning, and "
            "general shift rostering."
        ),
        "decision_variables": [
            {
                "name": "x_est",
                "description": "1 if employee e is assigned to shift s on day t, 0 otherwise",
                "type": "binary",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize total staffing cost (or maximize preference satisfaction)",
            "expression": "sum over e in E, s in S, t in T: c_es * x_est",
        },
        "constraints": [
            {
                "name": "demand_coverage",
                "description": "Minimum staffing level is met for each shift on each day",
                "expression": "sum over e in E: x_est >= R_st, for all s in S, t in T",
            },
            {
                "name": "one_shift_per_day",
                "description": "Each employee works at most one shift per day",
                "expression": "sum over s in S: x_est <= 1, for all e in E, t in T",
            },
            {
                "name": "max_hours_per_week",
                "description": "Total hours worked per employee per week does not exceed the maximum",
                "expression": "sum over s in S, t in week_w: h_s * x_est <= H_max, for all e in E, w in W",
            },
            {
                "name": "min_rest",
                "description": "Minimum rest period between consecutive shifts",
                "expression": "x_est + x_e_s2_(t+1) <= 1, for incompatible consecutive shift pairs (s, s2)",
            },
            {
                "name": "days_off",
                "description": "Each employee gets at least a minimum number of days off per week",
                "expression": "sum over t in week_w: (1 - sum over s in S: x_est) >= D_off, for all e in E, w in W",
            },
        ],
        "parameters": [
            {"name": "c_es", "description": "Cost of assigning employee e to shift s", "type": "float"},
            {"name": "R_st", "description": "Minimum number of employees required for shift s on day t", "type": "integer"},
            {"name": "h_s", "description": "Duration (hours) of shift s", "type": "float"},
            {"name": "H_max", "description": "Maximum hours an employee can work per week", "type": "float"},
            {"name": "D_off", "description": "Minimum days off per week per employee", "type": "integer"},
            {"name": "E", "description": "Set of employees", "type": "set"},
            {"name": "S", "description": "Set of shift types", "type": "set"},
            {"name": "T", "description": "Set of days in the planning horizon", "type": "set"},
        ],
        "tags": ["scheduling", "staff", "shift", "roster", "nurse", "workforce", "labor"],
        "source": "Ernst et al. (2004), Staff scheduling and rostering: A review; Burke et al. (2004)",
    },

    # 8. Assignment Problem (Linear Assignment)
    {
        "name": "Assignment Problem (Linear Assignment)",
        "alias": "LAP",
        "category": "assignment",
        "description": (
            "Assign n agents to n tasks in a one-to-one manner to minimize total "
            "assignment cost. Each agent is assigned to exactly one task and each "
            "task is assigned to exactly one agent. The constraint matrix is totally "
            "unimodular, so the LP relaxation always gives integer solutions."
        ),
        "decision_variables": [
            {
                "name": "x_ij",
                "description": "1 if agent i is assigned to task j, 0 otherwise",
                "type": "binary",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize total assignment cost",
            "expression": "sum over i in A, j in T: c_ij * x_ij",
        },
        "constraints": [
            {
                "name": "one_task_per_agent",
                "description": "Each agent is assigned to exactly one task",
                "expression": "sum over j in T: x_ij = 1, for all i in A",
            },
            {
                "name": "one_agent_per_task",
                "description": "Each task is assigned to exactly one agent",
                "expression": "sum over i in A: x_ij = 1, for all j in T",
            },
        ],
        "parameters": [
            {"name": "c_ij", "description": "Cost of assigning agent i to task j", "type": "float"},
            {"name": "A", "description": "Set of agents (|A| = n)", "type": "set"},
            {"name": "T", "description": "Set of tasks (|T| = n)", "type": "set"},
        ],
        "tags": ["assignment", "matching", "bipartite", "Hungarian", "one-to-one"],
        "source": "Kuhn (1955), The Hungarian method; Burkard, Dell'Amico & Martello (2009)",
    },

    # 9. Shortest Path Problem
    {
        "name": "Shortest Path Problem",
        "alias": "SPP",
        "category": "network",
        "description": (
            "Find the path of minimum total cost (or distance) from a source node "
            "to a destination node in a directed or undirected graph. Fundamental to "
            "routing, navigation, and network optimization."
        ),
        "decision_variables": [
            {
                "name": "x_ij",
                "description": "1 if arc (i,j) is on the shortest path, 0 otherwise (or flow on arc)",
                "type": "binary",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize total path cost from source to sink",
            "expression": "sum over (i,j) in A: c_ij * x_ij",
        },
        "constraints": [
            {
                "name": "source_flow",
                "description": "One unit of flow leaves the source node",
                "expression": "sum over j: x_sj - sum over j: x_js = 1",
            },
            {
                "name": "sink_flow",
                "description": "One unit of flow enters the sink node",
                "expression": "sum over i: x_it - sum over i: x_ti = -1",
            },
            {
                "name": "flow_conservation",
                "description": "Flow is conserved at all intermediate nodes",
                "expression": "sum over j: x_ij - sum over j: x_ji = 0, for all i in V \\ {s, t}",
            },
        ],
        "parameters": [
            {"name": "c_ij", "description": "Cost or distance of arc (i,j)", "type": "float"},
            {"name": "s", "description": "Source node", "type": "node"},
            {"name": "t", "description": "Sink (destination) node", "type": "node"},
            {"name": "V", "description": "Set of nodes", "type": "set"},
            {"name": "A", "description": "Set of arcs", "type": "set"},
        ],
        "tags": ["network", "shortest-path", "Dijkstra", "routing", "graph", "path"],
        "source": "Ahuja, Magnanti & Orlin (1993), Network Flows",
    },

    # 10. Minimum Spanning Tree
    {
        "name": "Minimum Spanning Tree",
        "alias": "MST",
        "category": "network",
        "description": (
            "Find a subset of edges in an undirected graph that connects all vertices "
            "with minimum total edge weight and no cycles. Used in network design, "
            "clustering, and approximation algorithms for other problems."
        ),
        "decision_variables": [
            {
                "name": "x_e",
                "description": "1 if edge e is included in the spanning tree, 0 otherwise",
                "type": "binary",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize total weight of selected edges",
            "expression": "sum over e in E: w_e * x_e",
        },
        "constraints": [
            {
                "name": "edge_count",
                "description": "A spanning tree on n vertices has exactly n-1 edges",
                "expression": "sum over e in E: x_e = |V| - 1",
            },
            {
                "name": "subtour_elimination",
                "description": "For every proper subset S of V, the number of selected edges within S is at most |S|-1 (prevents cycles)",
                "expression": "sum over e in E(S): x_e <= |S| - 1, for all S subset V, 2 <= |S| <= |V|-1",
            },
        ],
        "parameters": [
            {"name": "w_e", "description": "Weight (cost) of edge e", "type": "float"},
            {"name": "V", "description": "Set of vertices", "type": "set"},
            {"name": "E", "description": "Set of edges", "type": "set"},
        ],
        "tags": ["network", "spanning-tree", "Kruskal", "Prim", "graph", "connectivity"],
        "source": "Ahuja, Magnanti & Orlin (1993), Network Flows; Cormen et al. (2009), CLRS",
    },

    # 11. Lot Sizing Problem
    {
        "name": "Lot Sizing Problem",
        "alias": "LSP",
        "category": "planning",
        "description": (
            "Determine production quantities and timing over a finite planning horizon "
            "to satisfy known demand at minimum cost. Costs include fixed setup costs "
            "per production run, variable production costs, and inventory holding costs. "
            "The Wagner-Whitin model is the single-item uncapacitated variant."
        ),
        "decision_variables": [
            {
                "name": "x_t",
                "description": "Quantity produced in period t",
                "type": "continuous",
            },
            {
                "name": "y_t",
                "description": "1 if production occurs in period t (setup), 0 otherwise",
                "type": "binary",
            },
            {
                "name": "I_t",
                "description": "Inventory level at the end of period t",
                "type": "continuous",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize total setup costs, production costs, and inventory holding costs",
            "expression": "sum over t in T: (f_t * y_t + c_t * x_t + h_t * I_t)",
        },
        "constraints": [
            {
                "name": "inventory_balance",
                "description": "Inventory at end of period equals previous inventory plus production minus demand",
                "expression": "I_t = I_(t-1) + x_t - d_t, for all t in T",
            },
            {
                "name": "setup_forcing",
                "description": "Production can only occur if setup is performed (links x_t to y_t)",
                "expression": "x_t <= M_t * y_t, for all t in T",
            },
            {
                "name": "initial_inventory",
                "description": "Starting inventory is given",
                "expression": "I_0 = I_init",
            },
            {
                "name": "non_negativity",
                "description": "Production and inventory are non-negative",
                "expression": "x_t >= 0, I_t >= 0, for all t in T",
            },
        ],
        "parameters": [
            {"name": "f_t", "description": "Fixed setup cost in period t", "type": "float"},
            {"name": "c_t", "description": "Variable production cost per unit in period t", "type": "float"},
            {"name": "h_t", "description": "Inventory holding cost per unit per period", "type": "float"},
            {"name": "d_t", "description": "Demand in period t", "type": "float"},
            {"name": "M_t", "description": "Big-M for period t (e.g., sum of remaining demands)", "type": "float"},
            {"name": "I_init", "description": "Initial inventory level", "type": "float"},
            {"name": "T", "description": "Set of time periods in the planning horizon", "type": "set"},
        ],
        "tags": ["planning", "lot-sizing", "production", "inventory", "setup", "Wagner-Whitin", "MRP"],
        "source": "Wolsey (1998), Integer Programming; Pochet & Wolsey (2006), Production Planning by MIP",
    },

    # 12. Capacitated VRP (CVRP)
    {
        "name": "Capacitated Vehicle Routing Problem",
        "alias": "CVRP",
        "category": "routing",
        "description": (
            "Extension of VRP where all vehicles are identical with a fixed capacity. "
            "Determine routes for a homogeneous fleet departing from a single depot "
            "to serve all customers, where the total demand on each route must not "
            "exceed the vehicle capacity. Minimize total travel distance."
        ),
        "decision_variables": [
            {
                "name": "x_ij",
                "description": "Number of times arc (i,j) is traversed (or binary: 1 if arc is used)",
                "type": "binary",
            },
            {
                "name": "u_i",
                "description": "Cumulative demand served when arriving at customer i (for capacity/subtour elimination)",
                "type": "continuous",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize total travel distance",
            "expression": "sum over (i,j) in A: c_ij * x_ij",
        },
        "constraints": [
            {
                "name": "visit_once_in",
                "description": "Each customer has exactly one incoming arc",
                "expression": "sum over i in V: x_ij = 1, for all j in C",
            },
            {
                "name": "visit_once_out",
                "description": "Each customer has exactly one outgoing arc",
                "expression": "sum over j in V: x_ij = 1, for all i in C",
            },
            {
                "name": "depot_flow",
                "description": "Number of vehicles leaving the depot equals number returning",
                "expression": "sum over j in C: x_0j = sum over i in C: x_i0 = K",
            },
            {
                "name": "capacity_subtour",
                "description": "Cumulative demand bounds enforce both capacity and subtour elimination",
                "expression": "d_j <= u_j <= Q, and u_i + d_j - Q*(1 - x_ij) <= u_j, for all i,j in C",
            },
        ],
        "parameters": [
            {"name": "c_ij", "description": "Travel distance/cost from node i to node j", "type": "float"},
            {"name": "d_i", "description": "Demand of customer i", "type": "float"},
            {"name": "Q", "description": "Vehicle capacity (uniform for all vehicles)", "type": "float"},
            {"name": "K", "description": "Number of available vehicles", "type": "integer"},
            {"name": "V", "description": "Set of all nodes (depot 0 + customers)", "type": "set"},
            {"name": "C", "description": "Set of customers (V \\ {0})", "type": "set"},
            {"name": "A", "description": "Set of arcs", "type": "set"},
        ],
        "tags": ["routing", "vehicle", "capacitated", "CVRP", "fleet", "delivery", "depot"],
        "source": "Toth & Vigo (2014), Vehicle Routing: Problems, Methods, and Applications",
    },

    # 13. Multi-Commodity Flow
    {
        "name": "Multi-Commodity Flow",
        "alias": "MCF",
        "category": "network",
        "description": (
            "Route multiple distinct commodities through a shared network from their "
            "respective sources to sinks while respecting arc capacity limits. "
            "Used in telecommunications, logistics, and supply chain network design."
        ),
        "decision_variables": [
            {
                "name": "f_ij_k",
                "description": "Flow of commodity k on arc (i,j)",
                "type": "continuous",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize total routing cost across all commodities",
            "expression": "sum over k in K, (i,j) in A: c_ij_k * f_ij_k",
        },
        "constraints": [
            {
                "name": "flow_conservation",
                "description": "Flow conservation for each commodity at each node",
                "expression": "sum over j: f_ij_k - sum over j: f_ji_k = b_i_k, for all i in V, k in K",
            },
            {
                "name": "bundle_capacity",
                "description": "Total flow on each arc across all commodities cannot exceed arc capacity",
                "expression": "sum over k in K: f_ij_k <= u_ij, for all (i,j) in A",
            },
            {
                "name": "non_negativity",
                "description": "Flows are non-negative",
                "expression": "f_ij_k >= 0, for all (i,j) in A, k in K",
            },
        ],
        "parameters": [
            {"name": "c_ij_k", "description": "Cost per unit of flow of commodity k on arc (i,j)", "type": "float"},
            {"name": "u_ij", "description": "Capacity of arc (i,j)", "type": "float"},
            {"name": "b_i_k", "description": "Net supply/demand of commodity k at node i (positive=supply, negative=demand, zero=transshipment)", "type": "float"},
            {"name": "V", "description": "Set of nodes", "type": "set"},
            {"name": "A", "description": "Set of arcs", "type": "set"},
            {"name": "K", "description": "Set of commodities", "type": "set"},
        ],
        "tags": ["network", "multi-commodity", "flow", "routing", "telecommunications", "capacity"],
        "source": "Ahuja, Magnanti & Orlin (1993), Network Flows; Kennington & Helgason (1980)",
    },

    # 14. Set Covering Problem
    {
        "name": "Set Covering Problem",
        "alias": "SCP",
        "category": "assignment",
        "description": (
            "Select a minimum-cost collection of sets such that every element in "
            "the universe is covered by at least one selected set. Appears in crew "
            "scheduling, facility siting, and resource allocation."
        ),
        "decision_variables": [
            {
                "name": "x_j",
                "description": "1 if set j is selected, 0 otherwise",
                "type": "binary",
            },
        ],
        "objective": {
            "type": "minimize",
            "description": "Minimize total cost of selected sets",
            "expression": "sum over j in S: c_j * x_j",
        },
        "constraints": [
            {
                "name": "covering",
                "description": "Each element in the universe is covered by at least one selected set",
                "expression": "sum over j in S: a_ij * x_j >= 1, for all i in U",
            },
        ],
        "parameters": [
            {"name": "c_j", "description": "Cost of selecting set j", "type": "float"},
            {"name": "a_ij", "description": "1 if element i is contained in set j, 0 otherwise", "type": "binary"},
            {"name": "U", "description": "Universe of elements to be covered", "type": "set"},
            {"name": "S", "description": "Collection of candidate sets", "type": "set"},
        ],
        "tags": ["covering", "set-cover", "crew-scheduling", "selection", "minimum-cost"],
        "source": "Vazirani (2001), Approximation Algorithms; Caprara, Toth & Fischetti (2000)",
    },

    # 15. Maximum Flow Problem
    {
        "name": "Maximum Flow Problem",
        "alias": "MaxFlow",
        "category": "network",
        "description": (
            "Find the maximum amount of flow that can be sent from a source node to "
            "a sink node in a capacitated network. Equivalent by the max-flow min-cut "
            "theorem to finding the minimum capacity cut separating source and sink."
        ),
        "decision_variables": [
            {
                "name": "f_ij",
                "description": "Flow on arc (i,j)",
                "type": "continuous",
            },
            {
                "name": "F",
                "description": "Total flow value from source to sink",
                "type": "continuous",
            },
        ],
        "objective": {
            "type": "maximize",
            "description": "Maximize total flow from source to sink",
            "expression": "F",
        },
        "constraints": [
            {
                "name": "source_flow",
                "description": "Total flow out of the source equals F",
                "expression": "sum over j: f_sj - sum over j: f_js = F",
            },
            {
                "name": "sink_flow",
                "description": "Total flow into the sink equals F",
                "expression": "sum over i: f_it - sum over i: f_ti = -F",
            },
            {
                "name": "flow_conservation",
                "description": "Flow conservation at all intermediate nodes",
                "expression": "sum over j: f_ij - sum over j: f_ji = 0, for all i in V \\ {s, t}",
            },
            {
                "name": "capacity",
                "description": "Flow on each arc does not exceed its capacity",
                "expression": "0 <= f_ij <= u_ij, for all (i,j) in A",
            },
        ],
        "parameters": [
            {"name": "u_ij", "description": "Capacity of arc (i,j)", "type": "float"},
            {"name": "s", "description": "Source node", "type": "node"},
            {"name": "t", "description": "Sink node", "type": "node"},
            {"name": "V", "description": "Set of nodes", "type": "set"},
            {"name": "A", "description": "Set of arcs", "type": "set"},
        ],
        "tags": ["network", "max-flow", "min-cut", "capacity", "Ford-Fulkerson", "graph"],
        "source": "Ahuja, Magnanti & Orlin (1993), Network Flows; Ford & Fulkerson (1956)",
    },
]
