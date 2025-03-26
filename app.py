"""
Main Streamlit application for Flow Cytometry Cell Population Calculator

This app allows users to select an input cell count and calculates expected 
cell numbers and CV values for each population in the hierarchy.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
import sys

# Try to import optional dependencies
try:
    import networkx as nx
    import matplotlib.pyplot as plt
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False

# Add the current directory to the path to import custom modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import custom modules
from cell_database import CellHierarchyDB
from cv_calculator import calculate_cv, categorize_cv, generate_keeney_table

# Initialize the cell database
db = CellHierarchyDB()

def calculate_cell_counts(input_cells, hierarchy=None):
    """
    Calculate cell counts for each population based on input cells and hierarchy
    
    Args:
        input_cells: Number of input cells
        hierarchy: Optional custom hierarchy (uses database if None)
        
    Returns:
        Dictionary with cell counts for each population
    """
    if hierarchy is None:
        hierarchy = db.get_hierarchy()
    
    cell_counts = {}
    
    # First, calculate cell count for the root node (Leukocytes)
    # The input cells represent Single, Viable Cells that feed into Leukocytes
    root_node = db.get_root_node()
    cell_counts[root_node] = input_cells
    
    # Helper function to recursively calculate cell counts
    def calculate_children(node):
        if node in hierarchy:
            parent_count = cell_counts[node]
            
            for child in hierarchy[node]["children"]:
                # Calculate cell count based on proportion of parent
                child_proportion = hierarchy[child]["proportion"]
                cell_counts[child] = parent_count * child_proportion
                
                # Recursively calculate for this child's children
                calculate_children(child)
    
    # Start calculation from the root
    calculate_children(root_node)
    
    return cell_counts

def main():
    st.set_page_config(
        page_title="Flow Cytometry Cell Population Calculator",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Title and description
    st.title("Flow Cytometry Cell Population Calculator")
    
    with st.expander("About this app", expanded=False):
        st.markdown("""
        This app estimates the number of cells in each population based on the initial input cell count
        and calculates the expected coefficient of variation (CV) using Keeney's formula: r = (100/CV)².
        
        **Key features:**
        - Enter any input cell count (starting from 10K)
        - View estimated cell counts for each population in the hierarchy
        - Analyze expected CV for each population
        - Identify populations with potentially unreliable measurements (high CV)
        
        **References:**
        - Keeney et al. formula for CV calculation: r = (100/CV)²
        - Hierarchy based on Peripheral Blood Mononuclear Cell (PBMC) standard
        """)
    
    # Sidebar controls
    with st.sidebar:
        st.header("Input Settings")
        
        # Add starting cells in blood input
        st.subheader("Sample Processing")
        starting_cells = st.number_input(
            "Absolute number of cells in blood (per ml):",
            min_value=1000000,
            value=2500000,
            step=100000,
            format="%d",
            help="Typical value: 4-6 million cells/ml from healthy donor"
        )
        
        # Define processing efficiency percentages (based on the waterfall diagram)
        processing_steps = {
            "Pre-Stain": {"percent_of_previous": 1.0, "description": "Isolated PBMCs"}, 
            "Post-Stain": {"percent_of_previous": 0.35, "description": "After staining, ~65% cell loss"},
            "Events Acquired": {"percent_of_previous": 0.95, "description": "Cells successfully measured"},
            "Single, Viable Cells": {"percent_of_previous": 0.80, "description": "Final cells for analysis"} 
        }
        
        # Calculate waterfall of cell counts
        current_count = starting_cells
        cell_counts_waterfall = {}
        
        for step, info in processing_steps.items():
            current_count = int(current_count * info["percent_of_previous"])
            cell_counts_waterfall[step] = current_count
        
        # Display the waterfall as a table
        st.write("**Cell Processing Waterfall:**")
        waterfall_data = []
        for step, count in cell_counts_waterfall.items():
            percent_of_start = (count / starting_cells) * 100
            percent_of_previous = 100.0
            if step != "Pre-Stain":
                prev_step = list(processing_steps.keys())[list(processing_steps.keys()).index(step)-1]
                percent_of_previous = (count / cell_counts_waterfall[prev_step]) * 100
                
            waterfall_data.append({
                "Processing Step": step,
                "Cell Count": f"{count:,}",
                "% of Starting": f"{percent_of_start:.1f}%",
                "% of Previous Step": f"{percent_of_previous:.1f}%",
                "Description": processing_steps[step]["description"]
            })
        
        waterfall_df = pd.DataFrame(waterfall_data)
        st.dataframe(waterfall_df, use_container_width=True, hide_index=True)
        
        # Use the Single, Viable Cells as the input for Leukocytes
        input_cells = cell_counts_waterfall["Single, Viable Cells"]
        st.success(f"Analysis using {input_cells:,} Single, Viable Cells as input for Leukocytes")
        
        # Add Keeney's table reference
        st.subheader("Keeney's Reference Table")
        st.markdown("""
        This table shows the total number of events needed to achieve specific CV percentages
        for populations occurring at different frequencies.
        """)
        
        # Generate and display Keeney's table
        keeney_df = generate_keeney_table(
            desired_cvs=[1, 5, 10, 20],
            frequencies=[0.1, 0.01, 0.001, 0.0001]
        )
        
        # Format the table for display
        keeney_display = keeney_df.copy()
        keeney_display['Fraction'] = keeney_display['Fraction'].apply(lambda x: f"{x:.4f}")
        keeney_display = keeney_display.rename(columns={
            'Fraction': 'Frequency',
            '1:n': 'Ratio',
            'CV 1%': 'For 1% CV',
            'CV 5%': 'For 5% CV',
            'CV 10%': 'For 10% CV',
            'CV 20%': 'For 20% CV'
        })
        
        st.dataframe(keeney_display, use_container_width=True)
    
    # Calculate results
    cell_counts = calculate_cell_counts(input_cells)
    
    # Create dataframe with results
    results = []
    for cell_type, count in cell_counts.items():
        parent = db.get_parent(cell_type)
        parent_count = cell_counts[parent] if parent else None
        
        cv = calculate_cv(count)
        frequency = (count / parent_count if parent_count else 1.0) * 100
        
        results.append({
            "Population": cell_type,
            "Parent": parent if parent else "None",
            "Cell Count": int(count),
            "% of Parent": f"{frequency:.2f}%",
            "CV (%)": f"{cv:.2f}%", 
            "CV Value": cv,  # Raw value for sorting
            "CV Quality": categorize_cv(cv)
        })
    
    df = pd.DataFrame(results)
    
    # Sort by CV value for some displays
    df_sorted = df.sort_values(by="CV Value")
    
    # Create tabs for different views
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Table View", 
        "Tree View", 
        "CV Analysis",
        "Cell Distribution",
        "Cell Processing"
    ])
    
    with tab1:
        st.subheader("Estimated Cell Counts and CV")
        
        # Filter controls
        col1, col2 = st.columns(2)
        with col1:
            min_cv = st.slider("Min CV (%)", 0.0, 50.0, 0.0)
        with col2:
            max_cv = st.slider("Max CV (%)", 0.0, 50.0, 50.0)
        
        # Apply filters
        filtered_df = df[
            (df["CV Value"] >= min_cv) & 
            (df["CV Value"] <= max_cv)
        ].sort_values(by="CV Value")
        
        # Display columns needed for the table view
        display_df = filtered_df[["Population", "Parent", "Cell Count", "% of Parent", "CV (%)", "CV Quality"]]
        
        st.dataframe(display_df, use_container_width=True)
        
        # Allow downloading as CSV
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="Download as CSV",
            data=csv,
            file_name=f"cell_counts_{input_cells/1000:.0f}K.csv",
            mime="text/csv"
        )
    
    with tab2:
        st.subheader("Cell Population Hierarchy")
        
        # Add view type selection
        view_type = st.radio(
            "Select visualization type:",
            ["Interactive Tree", "Text Tree"],
            horizontal=True
        )
        
        # Create data for the tree visualization
        nodes = []
        edges = []
        node_labels = {}
        node_colors = []
        
        # Color mapping for CV quality
        color_map = {
            "Excellent (≤1%)": "#00FF00",  # Green
            "Good (1-5%)": "#90EE90",       # Light green
            "Fair (5-10%)": "#FFA500",      # Orange
            "Poor (10-20%)": "#FF4500",     # Red-Orange
            "Very Poor (>20%)": "#FF0000"   # Red
        }
        
        if view_type == "Interactive Tree":
            # Build nodes and edges list for tree layout
            root_node = db.get_root_node()
            node_to_index = {root_node: 0}  # Map node names to indices
            current_index = 1
            
            # First pass to collect nodes and create index mapping
            for cell_type, count in cell_counts.items():
                if cell_type not in node_to_index:
                    node_to_index[cell_type] = current_index
                    current_index += 1
                nodes.append(cell_type)
                
                parent = db.get_parent(cell_type)
                if parent:
                    edges.append((node_to_index[parent], node_to_index[cell_type]))
            
            # Create igraph Graph
            import igraph as ig
            G = ig.Graph(directed=True)
            G.add_vertices(len(nodes))
            G.add_edges(edges)
            
            # Get tree layout with basic tree layout
            layout = G.layout("tree", mode="out")
            
            # Get coordinates from layout and scale them
            coords = layout.coords
            scaled_coords = [[x*3, y] for x, y in coords]  # Triple the horizontal spacing
            
            # Convert scaled coordinates to position dict
            position = {k: scaled_coords[k] for k in range(len(nodes))}
            
            # Calculate Y range for inversion
            Y = [scaled_coords[k][1] for k in range(len(nodes))]
            M = max(Y) if Y else 0
            
            # Prepare node positions
            Xn = [position[k][0] for k in range(len(nodes))]
            Yn = [2*M-position[k][1] for k in range(len(nodes))]
            
            # Prepare edge positions
            Xe = []
            Ye = []
            for edge in edges:
                Xe += [position[edge[0]][0], position[edge[1]][0], None]
                Ye += [2*M-position[edge[0]][1], 2*M-position[edge[1]][1], None]
            
            # Create figure
            fig = go.Figure()
            
            # Add edges
            fig.add_trace(go.Scatter(
                x=Xe,
                y=Ye,
                mode='lines',
                line=dict(color='#888', width=1),
                hoverinfo='none'
            ))
            
            # Prepare node data
            node_colors = []
            node_sizes = []
            node_texts = []
            hover_texts = []
            text_positions = []  # Add variable text positions
            
            for i, node in enumerate(nodes):
                count = cell_counts[node]
                cv = calculate_cv(count)
                cv_quality = categorize_cv(cv)
                
                # Format cell count
                if count >= 1e6:
                    count_str = f"{count/1e6:.1f}M"
                else:
                    count_str = f"{count/1e3:.1f}K"
                
                # Add percentage if not root
                parent = db.get_parent(node)
                if parent:
                    parent_count = cell_counts[parent]
                    percentage = (count / parent_count) * 100
                    count_str += f" ({percentage:.1f}%)"
                
                node_colors.append(color_map[cv_quality])
                size = np.clip(np.log10(count) * 10, 20, 50)
                node_sizes.append(size)
                node_texts.append(node)
                hover_texts.append(f"{node}<br>{count_str}<br>CV: {cv:.1f}%")
                
                # Alternate text positions for better spacing
                siblings = [n for n in nodes if db.get_parent(n) == parent]
                if len(siblings) > 1:
                    idx = siblings.index(node)
                    if idx % 2 == 0:
                        text_positions.append("bottom right")
                    else:
                        text_positions.append("bottom left")
                else:
                    text_positions.append("bottom center")
            
            # Add nodes with adjusted text positioning
            fig.add_trace(go.Scatter(
                x=Xn,
                y=Yn,
                mode='markers+text',
                marker=dict(
                    size=node_sizes,
                    color=node_colors,
                    line=dict(color='white', width=2)
                ),
                text=node_texts,
                textposition=text_positions,
                hovertext=hover_texts,
                hoverinfo='text'
            ))
            
            # Update layout
            fig.update_layout(
                title="Cell Population Hierarchy Tree",
                showlegend=False,
                hovermode='closest',
                dragmode='pan',
                margin=dict(b=20, l=5, r=5, t=40),
                height=800,
                plot_bgcolor='white',
                xaxis=dict(
                    showgrid=False,
                    zeroline=False,
                    showticklabels=False,
                    scaleanchor="y",
                    scaleratio=1,
                ),
                yaxis=dict(
                    showgrid=False,
                    zeroline=False,
                    showticklabels=False,
                )
            )
            
            # Enable all interactive features
            st.plotly_chart(fig, use_container_width=True, config={
                'scrollZoom': True,     # Enable zoom with mouse wheel
                'displayModeBar': True, # Always show the mode bar
                'modeBarButtonsToAdd': [
                    'pan2d',
                    'zoomIn2d',
                    'zoomOut2d',
                    'resetScale2d'
                ]
            })
            
            # Add legend for CV quality colors
            st.subheader("CV Quality Legend")
            legend_cols = st.columns(len(color_map))
            for col, (quality, color) in zip(legend_cols, color_map.items()):
                col.markdown(f"""
                <div style="
                    width: 20px;
                    height: 20px;
                    background-color: {color};
                    display: inline-block;
                    margin-right: 5px;
                "></div> {quality}
                """, unsafe_allow_html=True)
        
        else:  # Text tree view
            # Function to build text tree recursively
            def build_text_tree(node, level=0, is_last=False, prefix=""):
                indent = ""
                if level > 0:
                    indent = prefix + ("└── " if is_last else "├── ")
                
                # Get cell count and CV
                count = cell_counts[node]
                cv = calculate_cv(count)
                cv_quality = categorize_cv(cv)
                
                # Format cell count
                if count >= 1e6:
                    count_str = f"{count/1e6:.1f}M"
                else:
                    count_str = f"{count/1e3:.1f}K"
                
                # Add percentage if not root
                parent = db.get_parent(node)
                if parent:
                    parent_count = cell_counts[parent]
                    percentage = (count / parent_count) * 100
                    percentage_str = f" ({percentage:.1f}%)"
                else:
                    percentage_str = ""
                
                # Create colored circle for CV quality
                color = color_map[cv_quality]
                circle = f'<span style="color:{color}">●</span>'
                
                line = f"{indent}{node}: {count_str}{percentage_str} - CV: {cv:.2f}% {circle}"
                tree_lines.append(line)
                
                # Get children
                children = db.get_children(node)
                if children:
                    new_prefix = prefix
                    if level > 0:
                        new_prefix = prefix + ("    " if is_last else "│   ")
                    
                    for i, child in enumerate(children):
                        is_last_child = (i == len(children) - 1)
                        build_text_tree(child, level + 1, is_last_child, new_prefix)
            
            # Start building the tree
            tree_lines = []
            build_text_tree(db.get_root_node())
            
            # Create a container with scrollable content
            st.markdown("""
            <style>
            .tree-container {
                max-height: 800px;
                overflow-y: auto;
                font-family: monospace;
                white-space: nowrap;
                padding: 10px;
                background-color: #f5f5f5;
                border-radius: 5px;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # Display the tree lines with HTML for colored markers
            text_tree_html = "<div class='tree-container'>"
            for line in tree_lines:
                text_tree_html += f"{line}<br>"
            text_tree_html += "</div>"
            
            st.markdown(text_tree_html, unsafe_allow_html=True)
            
            # Add legend for CV quality colors
            st.subheader("CV Quality Legend")
            legend_cols = st.columns(len(color_map))
            for col, (quality, color) in zip(legend_cols, color_map.items()):
                col.markdown(f"""
                <span style="
                    color: {color};
                    font-size: 20px;
                ">●</span> {quality}
                """, unsafe_allow_html=True)
    
    with tab3:
        st.subheader("CV Analysis")
        
        # Filter for leaf nodes (populations with no children)
        leaf_nodes = [cell for cell in db.get_hierarchy() if not db.get_children(cell)]
        leaf_df = df[df["Population"].isin(leaf_nodes)].sort_values(by="CV Value")
        
        # Create a bar chart of CVs for leaf populations
        fig = px.bar(
            leaf_df,
            x="Population",
            y="CV Value",
            color="CV Quality",
            title="Coefficient of Variation by Cell Population (Leaf Nodes Only)",
            labels={"CV Value": "Coefficient of Variation (%)"},
            hover_data=["Cell Count", "% of Parent"]
        )
        
        fig.update_layout(
            xaxis={'categoryorder':'total ascending'},
            height=600
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Show table of populations with poor CV
        st.subheader("Populations with Higher CV (>10%)")
        high_cv_df = df[df["CV Value"] > 10].sort_values(by="CV Value", ascending=False)
        
        if not high_cv_df.empty:
            st.dataframe(high_cv_df[["Population", "Cell Count", "% of Parent", "CV (%)", "CV Quality"]])
            
            st.info("""
            💡 **Tip:** Populations with high CV values may have unreliable measurements. 
            Consider increasing the total input cells or pooling samples if precise measurements 
            of these populations are important.
            """)
        else:
            st.success("No populations with CV >10% found with current input cells")
    
    with tab4:
        st.subheader("Cell Distribution")
        
        # Create a treemap of the cell distribution
        fig = px.treemap(
            df,
            path=['Parent', 'Population'],
            values='Cell Count',
            color='CV Value',
            color_continuous_scale='RdYlGn_r',
            title=f"Cell Distribution for {input_cells/1000:.1f}K Input Cells",
            hover_data=['CV (%)', 'CV Quality']
        )
        
        fig.update_layout(height=700)
        st.plotly_chart(fig, use_container_width=True)
        
        # Also add a sunburst chart as an alternative visualization
        fig2 = px.sunburst(
            df,
            path=['Parent', 'Population'],
            values='Cell Count',
            color='CV Value',
            color_continuous_scale='RdYlGn_r',
            title=f"Sunburst Chart of Cell Distribution ({input_cells/1000:.1f}K Input Cells)",
            hover_data=['CV (%)', 'CV Quality']
        )
        
        fig2.update_layout(height=700)
        st.plotly_chart(fig2, use_container_width=True)
    
    with tab5:
        st.subheader("Cell Processing Waterfall")
        
        st.markdown("""
        This diagram shows how cells are processed from the initial blood sample through
        various steps until they become usable Single, Viable Cells for analysis.
        """)
        
        # Display the waterfall data as a larger table
        waterfall_data = []
        for step, count in cell_counts_waterfall.items():
            percent_of_start = (count / starting_cells) * 100
            percent_of_previous = 100
            if step != "Pre-Stain":
                prev_step = list(processing_steps.keys())[list(processing_steps.keys()).index(step)-1]
                percent_of_previous = (count / cell_counts_waterfall[prev_step]) * 100
                
            waterfall_data.append({
                "Processing Step": step,
                "Cell Count": f"{count:,}",
                "% of Starting": f"{percent_of_start:.1f}%",
                "% of Previous Step": f"{percent_of_previous:.1f}%",
                "Description": processing_steps[step]["description"]
            })
        
        waterfall_df = pd.DataFrame(waterfall_data)
        st.dataframe(waterfall_df, use_container_width=True, hide_index=True)
        
        # Create a simple bar chart instead of waterfall
        fig = px.bar(
            x=list(cell_counts_waterfall.keys()),
            y=list(cell_counts_waterfall.values()),
            labels={"x": "Processing Step", "y": "Cell Count"},
            title="Cell Counts Through Processing Steps",
            text=[f"{count:,}" for count in cell_counts_waterfall.values()]
        )
        
        fig.update_traces(
            textposition="outside",
            marker_color="#1f77b4"
        )
        
        fig.update_layout(
            height=500,
            yaxis_title="Cell Count",
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Add explanation about the final cells
        st.info(f"""
        **Final Analysis Population:** The resulting {cell_counts_waterfall['Single, Viable Cells']:,} 
        Single, Viable Cells become the input for the Leukocytes population, which is the root node 
        for all subsequent analysis in the hierarchy.
        """)

if __name__ == "__main__":
    main()