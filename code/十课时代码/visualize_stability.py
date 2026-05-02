"""
可视化因子稳定性诊断结果
功能：
1. 绘制因子相关性热力图 (Correlation Matrix Heatmap)
2. 绘制因子 VIF 柱状图 (Variance Inflation Factor Bar Chart)
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Set plot style
plt.style.use('seaborn-v0_8')

class StabilityVisualizer:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_correlation_heatmap(self, corr_file: str, save_name: str = "factor_correlation.png"):
        """Plot correlation heatmap with English labels"""
        if not Path(corr_file).exists():
            print(f"⚠️ File not found: {corr_file}")
            return

        df = pd.read_csv(corr_file, index_col=0)
        
        plt.figure(figsize=(10, 8))
        sns.heatmap(
            df, 
            annot=True, 
            fmt=".2f", 
            cmap="coolwarm", 
            center=0,
            vmin=-1, 
            vmax=1,
            square=True,
            linewidths=.5
        )
        plt.title("Factor Correlation Matrix (Spearman)", fontsize=15)
        plt.tight_layout()
        
        save_path = self.output_dir / save_name
        plt.savefig(save_path, dpi=300)
        print(f"✅ Correlation heatmap saved: {save_path}")
        plt.close()

    def plot_vif_bar(self, vif_file: str, save_name: str = "factor_vif.png"):
        """Plot VIF bar chart with English labels"""
        if not Path(vif_file).exists():
            print(f"⚠️ File not found: {vif_file}")
            return

        df = pd.read_csv(vif_file)
        
        plt.figure(figsize=(10, 6))
        bars = plt.bar(df['factor'], df['vif'], color='skyblue', edgecolor='navy')
        
        # Add threshold lines
        plt.axhline(y=5, color='orange', linestyle='--', label='Threshold=5 (Warning)')
        plt.axhline(y=10, color='red', linestyle='--', label='Threshold=10 (Danger)')
        
        plt.title("Factor VIF Analysis", fontsize=15)
        plt.ylabel("VIF Value")
        plt.xticks(rotation=45)
        plt.legend()
        
        # Annotate bars with values
        for bar in bars:
            height = bar.get_height()
            plt.text(
                bar.get_x() + bar.get_width()/2., 
                height,
                f'{height:.2f}',
                ha='center', va='bottom'
            )

        plt.tight_layout()
        save_path = self.output_dir / save_name
        plt.savefig(save_path, dpi=300)
        print(f"✅ VIF bar chart saved: {save_path}")
        plt.close()

    def plot_rolling_ic(self, ic_file: str, save_name: str = "ic_rolling.png"):
        """Plot rolling IC time series"""
        if not Path(ic_file).exists():
            print(f"⚠️ File not found: {ic_file}")
            return

        df = pd.read_csv(ic_file, index_col=0, parse_dates=True)
        
        plt.figure(figsize=(12, 6))
        
        for col in df.columns:
            plt.plot(df.index, df[col], label=col)
            
        plt.title("Rolling IC Time Series (20-day)", fontsize=15)
        plt.ylabel("IC Value")
        plt.xlabel("Date")
        plt.axhline(0, color='black', linestyle='--', linewidth=0.8)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        save_path = self.output_dir / save_name
        plt.savefig(save_path, dpi=300)
        print(f"✅ Rolling IC plot saved: {save_path}")
        plt.close()


if __name__ == "__main__":
    # 输入数据目录 (即 stability_diagnostics.py 的输出目录)
    INPUT_DIR = "./outputs/stability_diagnostics"
    # 图片保存目录
    OUTPUT_DIR = "./outputs/stability_diagnostics" 

    viz = StabilityVisualizer(OUTPUT_DIR)
    
    # 1. 绘制相关性
    viz.plot_correlation_heatmap(f"{INPUT_DIR}/factor_corr.csv")
    
    # 2. 绘制 VIF
    viz.plot_vif_bar(f"{INPUT_DIR}/factor_vif.csv")

    # 3. 绘制滚动 IC
    viz.plot_rolling_ic(f"{INPUT_DIR}/ic_rolling.csv")
