"""
Component for displaying Reverse Analysis settings and calculations in the sidebar.
"""

import streamlit as st
from cell_database import CellHierarchyDB
from streamlit_tree_select import tree_select
from config.settings import (
    DEFAULT_POST_STAIN_PCT,
    DEFAULT_EVENTS_ACQUIRED_PCT,
    DEFAULT_VIABLE_CELLS_PCT,
    MIN_STARTING_CELLS,
    DEFAULT_STARTING_CELLS # Added for default return
)

def build_tree_select_nodes(node_name, db):
    """Recursively build node structure for streamlit-tree-select."""
    # This helper function might be better placed in a utils file if used elsewhere,
    # but keeping it here for now for simplicity.
    children_names = db.get_children(node_name)
    children_nodes = []
    if children_names:
        children_nodes = [build_tree_select_nodes(child, db) for child in children_names]
    return {"label": node_name, "value": node_name, "children": children_nodes}

def get_cumulative_proportion(population, db, hierarchy):
    """Calculate the cumulative proportion of a population relative to the root."""
    proportion = 1.0
    current = population
    parent = db.get_parent(current)
    # Traverse up the tree until the root's parent (None) is reached
    while parent is not None:
        if current in hierarchy:
            # Check if the node exists and has a proportion defined
            if "proportion" in hierarchy[current]:
                 proportion *= hierarchy[current]["proportion"]
            else:
                 st.error(f"Error: Node {current} missing 'proportion' in hierarchy definition.")
                 return 0.0
        else:
            # This case should ideally not happen if db methods are correct
            st.error(f"Error: Node {current} not found in hierarchy definition during proportion calculation.")
            return 0.0
        current = parent
        parent = db.get_parent(current) # Get the next parent

    # If the loop finishes, 'current' should be the root node.
    # Check if root itself has a proportion (usually 1.0, handled implicitly if traversal is correct)
    # No need to multiply by root proportion if it's 1.0 and traversal stops correctly.
    return proportion


def display_reverse_analysis_sidebar(db: CellHierarchyDB):
    """
    Displays the Target Population and CV settings, performs calculations,
    and returns the required starting_cells.
    """
    st.subheader("Target Population Settings")

    # Prepare data for tree select
    root_node_name = db.get_root_node()
    nodes_for_select = [build_tree_select_nodes(root_node_name, db)] if root_node_name else []

    # Use tree_select instead of selectbox
    selected_node = tree_select(
        nodes_for_select,
        show_expand_all=True,
    )

    # Extract the selected value
    target_population = selected_node['selected'][0] if selected_node and selected_node['selected'] else None

    # Default selection handling
    if not target_population:
        leaf_populations = [cell for cell in db.get_hierarchy() if not db.get_children(cell)]
        target_population = leaf_populations[0] if leaf_populations else db.get_root_node()
        st.warning(f"No population selected, defaulting to: {target_population}. Please select a target.")
        # Return a default value if no target is properly selected yet
        return DEFAULT_STARTING_CELLS

    # --- Calculations Section ---
    hierarchy = db.get_hierarchy() # Get hierarchy once

    target_cv = st.slider(
        "Target CV (%)",
        min_value=0.1,
        max_value=100.0,
        value=20.0,
        step=0.1,
        help="Desired coefficient of variation for the target population",
        key=f"target_cv_{target_population}" # Unique key per population
    )

    population_frequency = get_cumulative_proportion(target_population, db, hierarchy)

    if population_frequency is not None and population_frequency >= 0:
        st.info(f"""
        Based on the hierarchy, {target_population} represents approximately
        {population_frequency:.4%} of total leukocytes
        """)
    else:
        # Handle error from get_cumulative_proportion if needed
        st.error("Could not determine population frequency.")
        return DEFAULT_STARTING_CELLS # Return default if frequency calculation failed


    # Calculate required events
    required_events = float('inf')
    if population_frequency > 0:
        required_events = int((100/target_cv)**2 / population_frequency)
    else:
        st.error(f"Cannot calculate required events for {target_population} with zero or invalid frequency.")
        # Decide if we should proceed or return default

    # Get current processing efficiencies from session state
    post_stain_pct_rev = st.session_state.get("post_stain_pct", DEFAULT_POST_STAIN_PCT)
    events_acquired_pct_rev = st.session_state.get("events_acquired_pct", DEFAULT_EVENTS_ACQUIRED_PCT)
    viable_cells_pct_rev = st.session_state.get("viable_cells_pct", DEFAULT_VIABLE_CELLS_PCT)
    total_efficiency = (post_stain_pct_rev/100) * (events_acquired_pct_rev/100) * (viable_cells_pct_rev/100)

    # Calculate required input cells
    required_input_cells = float('inf')
    if required_events != float('inf') and total_efficiency > 0 :
        required_input_cells = int(required_events / total_efficiency)
        st.success(f"""
        To achieve {target_cv}% CV for {target_population}:
        - Required events for target population: {required_events:,}
        - Required input cells (Pre-Stain): {required_input_cells:,}

        (Using current processing efficiencies: {total_efficiency:.1%} overall)
        """)
    elif total_efficiency <= 0:
        st.error("Cannot calculate required input cells with zero processing efficiency.")
    elif required_events == float('inf'):
        # Error already shown for frequency=0 case
        pass # Avoid duplicate error message
    else:
        # Catch unexpected cases
         st.error("An error occurred during input cell calculation.")


    # Return the calculated starting cells (or a default minimum if calculation failed)
    return required_input_cells if required_input_cells != float('inf') else MIN_STARTING_CELLS 