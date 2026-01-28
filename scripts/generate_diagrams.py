#!/usr/bin/env python3
"""Generate architecture and data flow diagrams as PNG images."""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np


def create_architecture_diagram():
    """Create the architecture diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis('off')
    ax.set_aspect('equal')
    
    # Colors
    user_color = '#E3F2FD'
    frontend_color = '#BBDEFB'
    backend_color = '#90CAF9'
    data_color = '#64B5F6'
    external_color = '#42A5F5'
    
    # Title
    ax.text(6, 7.7, 'System Architecture', fontsize=16, fontweight='bold', ha='center')
    
    # Users
    user_box = FancyBboxPatch((5, 6.8), 2, 0.6, boxstyle="round,pad=0.05", 
                               facecolor=user_color, edgecolor='black', linewidth=1.5)
    ax.add_patch(user_box)
    ax.text(6, 7.1, 'Users', fontsize=11, ha='center', va='center', fontweight='bold')
    
    # Arrow from users
    ax.annotate('', xy=(6, 6.3), xytext=(6, 6.8),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    
    # Frontends
    frontends = [
        ('faa.e-cfr.app', 1.5),
        ('nrc.e-cfr.app', 5),
        ('dod.e-cfr.app', 8.5),
    ]
    for name, x in frontends:
        box = FancyBboxPatch((x, 5.5), 2.5, 0.7, boxstyle="round,pad=0.05",
                             facecolor=frontend_color, edgecolor='black', linewidth=1.5)
        ax.add_patch(box)
        ax.text(x + 1.25, 5.85, name, fontsize=9, ha='center', va='center', fontweight='bold')
    
    # Arrows from frontends to backend
    for _, x in frontends:
        ax.annotate('', xy=(6, 4.8), xytext=(x + 1.25, 5.5),
                    arrowprops=dict(arrowstyle='->', color='black', lw=1))
    
    # SolidJS label
    ax.text(6, 6.35, 'SolidJS + WebSocket', fontsize=8, ha='center', va='center', style='italic', color='gray')
    
    # Backend
    backend_box = FancyBboxPatch((3.5, 3.8), 5, 1, boxstyle="round,pad=0.05",
                                  facecolor=backend_color, edgecolor='black', linewidth=2)
    ax.add_patch(backend_box)
    ax.text(6, 4.5, 'FastAPI Backend', fontsize=11, ha='center', va='center', fontweight='bold')
    ax.text(6, 4.1, '+ Claude Sonnet Orchestrator', fontsize=9, ha='center', va='center')
    
    # Data layer boxes
    data_boxes = [
        ('Azure\nSearch', 0.8, 1.5),
        ('Blob\nCache', 3.0, 1.5),
        ('PostgreSQL', 5.2, 1.5),
        ('eCFR\nAPI', 7.4, 1.5),
        ('DRS/ADAMS\nAPIs', 9.6, 1.5),
    ]
    
    for name, x, y in data_boxes:
        color = data_color if x < 7 else external_color
        box = FancyBboxPatch((x, y), 1.8, 1.2, boxstyle="round,pad=0.05",
                             facecolor=color, edgecolor='black', linewidth=1.5)
        ax.add_patch(box)
        ax.text(x + 0.9, y + 0.6, name, fontsize=8, ha='center', va='center', fontweight='bold')
    
    # Arrows from backend to data layer
    for name, x, y in data_boxes:
        ax.annotate('', xy=(x + 0.9, y + 1.2), xytext=(6, 3.8),
                    arrowprops=dict(arrowstyle='->', color='black', lw=1))
    
    # Labels
    ax.text(3.5, 0.9, 'Internal Services', fontsize=9, ha='center', style='italic', color='gray')
    ax.text(9.4, 0.9, 'External APIs', fontsize=9, ha='center', style='italic', color='gray')
    
    # Divider line
    ax.axvline(x=6.8, ymin=0.12, ymax=0.35, color='gray', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig('/Users/tudor/src/faa-agent/architecture_diagram.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print("Created: architecture_diagram.png")


def create_dataflow_diagram():
    """Create the data flow diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(12, 7))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7)
    ax.axis('off')
    ax.set_aspect('equal')
    
    # Colors
    input_color = '#E8F5E9'
    process_color = '#C8E6C9'
    decision_color = '#FFF9C4'
    action_color = '#BBDEFB'
    output_color = '#E1BEE7'
    
    # Title
    ax.text(6, 6.7, 'Data Flow', fontsize=16, fontweight='bold', ha='center')
    
    # Step 1: Question
    box1 = FancyBboxPatch((0.5, 5.2), 2, 0.8, boxstyle="round,pad=0.05",
                          facecolor=input_color, edgecolor='black', linewidth=1.5)
    ax.add_patch(box1)
    ax.text(1.5, 5.6, '1. Question', fontsize=10, ha='center', va='center', fontweight='bold')
    
    # Arrow
    ax.annotate('', xy=(3, 5.6), xytext=(2.5, 5.6),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    
    # Step 2: Claude Orchestrator
    box2 = FancyBboxPatch((3, 5.2), 2.5, 0.8, boxstyle="round,pad=0.05",
                          facecolor=process_color, edgecolor='black', linewidth=1.5)
    ax.add_patch(box2)
    ax.text(4.25, 5.6, '2. Claude\nOrchestrator', fontsize=9, ha='center', va='center', fontweight='bold')
    
    # Arrow
    ax.annotate('', xy=(6, 5.6), xytext=(5.5, 5.6),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    
    # Step 3: Tool Selection
    box3 = FancyBboxPatch((6, 5.2), 2, 0.8, boxstyle="round,pad=0.05",
                          facecolor=decision_color, edgecolor='black', linewidth=1.5)
    ax.add_patch(box3)
    ax.text(7, 5.6, '3. Tool\nSelection', fontsize=9, ha='center', va='center', fontweight='bold')
    
    # Branching arrows down
    ax.annotate('', xy=(5.5, 4.2), xytext=(7, 5.2),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    ax.annotate('', xy=(8.5, 4.2), xytext=(7, 5.2),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    
    # Search branch
    box4a = FancyBboxPatch((4.5, 3.4), 2, 0.8, boxstyle="round,pad=0.05",
                           facecolor=action_color, edgecolor='black', linewidth=1.5)
    ax.add_patch(box4a)
    ax.text(5.5, 3.8, 'Search\nAzure Index', fontsize=9, ha='center', va='center', fontweight='bold')
    
    # Fetch branch
    box4b = FancyBboxPatch((7.5, 3.4), 2, 0.8, boxstyle="round,pad=0.05",
                           facecolor=action_color, edgecolor='black', linewidth=1.5)
    ax.add_patch(box4b)
    ax.text(8.5, 3.8, 'Fetch\nDocument', fontsize=9, ha='center', va='center', fontweight='bold')
    
    # Arrow down from Fetch
    ax.annotate('', xy=(8.5, 2.6), xytext=(8.5, 3.4),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    
    # Cache check
    box5 = FancyBboxPatch((7.5, 1.8), 2, 0.8, boxstyle="round,pad=0.05",
                          facecolor=decision_color, edgecolor='black', linewidth=1.5)
    ax.add_patch(box5)
    ax.text(8.5, 2.2, 'Cache\nHit?', fontsize=9, ha='center', va='center', fontweight='bold')
    
    # Cache hit - return
    ax.annotate('', xy=(6.5, 2.2), xytext=(7.5, 2.2),
                arrowprops=dict(arrowstyle='->', color='green', lw=1.5))
    ax.text(7, 2.5, 'Yes', fontsize=8, ha='center', color='green')
    
    # Return cached
    box6a = FancyBboxPatch((4.5, 1.8), 2, 0.8, boxstyle="round,pad=0.05",
                           facecolor='#C8E6C9', edgecolor='black', linewidth=1.5)
    ax.add_patch(box6a)
    ax.text(5.5, 2.2, 'Return\nCached', fontsize=9, ha='center', va='center', fontweight='bold')
    
    # Cache miss - external API
    ax.annotate('', xy=(10, 1.4), xytext=(9.5, 1.8),
                arrowprops=dict(arrowstyle='->', color='red', lw=1.5))
    ax.text(10, 1.9, 'No', fontsize=8, ha='center', color='red')
    
    # External API call
    box6b = FancyBboxPatch((9.5, 0.6), 2, 0.8, boxstyle="round,pad=0.05",
                           facecolor='#FFCDD2', edgecolor='black', linewidth=1.5)
    ax.add_patch(box6b)
    ax.text(10.5, 1, 'External\nAPI Call', fontsize=9, ha='center', va='center', fontweight='bold')
    
    # Arrow to cache + index
    ax.annotate('', xy=(8.5, 0.6), xytext=(9.5, 1),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    
    # Cache + Auto-index
    box7 = FancyBboxPatch((6.5, 0.2), 2, 0.8, boxstyle="round,pad=0.05",
                          facecolor='#B3E5FC', edgecolor='black', linewidth=1.5)
    ax.add_patch(box7)
    ax.text(7.5, 0.6, 'Cache +\nAuto-Index', fontsize=9, ha='center', va='center', fontweight='bold')
    
    # Converge to response
    ax.annotate('', xy=(3, 2.2), xytext=(4.5, 2.2),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    ax.annotate('', xy=(3, 2.2), xytext=(5.5, 3.4),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    ax.annotate('', xy=(3, 2.2), xytext=(6.5, 0.6),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    
    # Response
    box8 = FancyBboxPatch((0.8, 1.8), 2.2, 0.8, boxstyle="round,pad=0.05",
                          facecolor=output_color, edgecolor='black', linewidth=2)
    ax.add_patch(box8)
    ax.text(1.9, 2.2, 'Response +\nCitations', fontsize=10, ha='center', va='center', fontweight='bold')
    
    # Arrow to user
    ax.annotate('', xy=(1.9, 1), xytext=(1.9, 1.8),
                arrowprops=dict(arrowstyle='->', color='black', lw=2))
    
    # Stream to user
    box9 = FancyBboxPatch((0.8, 0.2), 2.2, 0.8, boxstyle="round,pad=0.05",
                          facecolor=input_color, edgecolor='black', linewidth=1.5)
    ax.add_patch(box9)
    ax.text(1.9, 0.6, 'Stream to\nUser', fontsize=10, ha='center', va='center', fontweight='bold')
    
    # Self-improving note
    ax.text(7.5, -0.2, '↻ Self-improving: fetched docs auto-index for future queries', 
            fontsize=8, ha='center', style='italic', color='#1565C0')
    
    plt.tight_layout()
    plt.savefig('/Users/tudor/src/faa-agent/dataflow_diagram.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print("Created: dataflow_diagram.png")


if __name__ == "__main__":
    create_architecture_diagram()
    create_dataflow_diagram()
    print("\nDiagrams saved to /Users/tudor/src/faa-agent/")
