"""
Report generation for cryptocurrency tax calculations.

Generates:
- CSV ledger with transaction details
- CSV summary by year
- JSON export for integration
- Human-readable text reports
"""

import csv
import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from models import TaxReport, NormalizedTransaction

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates various report formats from TaxReport.
    
    Supports:
    - CSV detailed ledger (all transactions)
    - CSV annual summary
    - JSON export (machine-readable)
    - Text summary (human-readable)
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize report generator.
        
        Args:
            output_dir: Directory for output files. If None, uses current directory.
        """
        self.output_dir = output_dir or Path(".")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_all(
        self,
        report: TaxReport,
        prefix: str = "tax_report",
    ) -> dict[str, Path]:
        """
        Generate all report formats.
        
        Args:
            report: TaxReport to generate from
            prefix: Filename prefix
            
        Returns:
            Dictionary mapping report type to file path
        """
        results = {}
        
        try:
            results['ledger_csv'] = self.generate_ledger_csv(report, prefix)
            logger.info(f"Generated ledger CSV: {results['ledger_csv']}")
        except Exception as e:
            logger.error(f"Failed to generate ledger CSV: {e}")
        
        try:
            results['summary_csv'] = self.generate_summary_csv(report, prefix)
            logger.info(f"Generated summary CSV: {results['summary_csv']}")
        except Exception as e:
            logger.error(f"Failed to generate summary CSV: {e}")
        
        try:
            results['json'] = self.generate_json(report, prefix)
            logger.info(f"Generated JSON export: {results['json']}")
        except Exception as e:
            logger.error(f"Failed to generate JSON export: {e}")
        
        try:
            results['text'] = self.generate_text_summary(report, prefix)
            logger.info(f"Generated text summary: {results['text']}")
        except Exception as e:
            logger.error(f"Failed to generate text summary: {e}")
        
        return results
    
    def generate_ledger_csv(
        self,
        report: TaxReport,
        prefix: str = "tax_report",
    ) -> Path:
        """
        Generate detailed transaction ledger in CSV format.
        
        Columns:
        - Data: Transaction date
        - Operacja: Operation type
        - Waluta/Krypto: Asset
        - Ilość: Amount
        - Typ: Cost/Revenue/Ignored
        - Kurs_NBP: Exchange rate used
        - Wartość_PLN: PLN value
        - Czy_Podatkowe: Whether taxable
        
        Args:
            report: TaxReport
            prefix: Filename prefix
            
        Returns:
            Path to generated CSV file
        """
        filename = self.output_dir / f"{prefix}_ledger.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Data',
                'Operacja',
                'Waluta',
                'Ilość',
                'Typ_Podatkowy',
                'Kurs_NBP_T1',
                'Wartość_PLN',
                'Czy_Opodatkowany',
            ])
            
            # Transactions sorted by date
            for txn in sorted(report.transactions, key=lambda t: t.timestamp):
                is_taxable = txn.tax_event_type.value != 'IGNOROWANE'
                
                writer.writerow([
                    txn.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    txn.operation_type.value,
                    txn.asset,
                    f"{txn.amount:.8f}",
                    txn.tax_event_type.value,
                    f"{txn.exchange_rate:.6f}" if txn.exchange_rate else "N/A",
                    f"{txn.pln_value:.2f}" if txn.pln_value else "0.00",
                    "TAK" if is_taxable else "NIE",
                ])
        
        logger.info(f"Ledger CSV generated: {filename}")
        return filename
    
    def generate_summary_csv(
        self,
        report: TaxReport,
        prefix: str = "tax_report",
    ) -> Path:
        """
        Generate annual tax summary in CSV format.
        
        Columns:
        - Rok: Tax year
        - Liczba_Transakcji: Number of transactions
        - Przychód_PLN: Revenue from crypto sales
        - Koszt_PLN: Cost of crypto purchases
        - Opłaty_PLN: Fees paid
        - Razem_Koszt: Total cost (including fees)
        - Dochód_Strata: Net income or loss
        - Strata_z_Poprzedniego_Roku: Loss carried forward
        - Dochód_Do_Opodatkowania: Taxable income
        - Podatek_19_Procent: Tax due at 19%
        
        Args:
            report: TaxReport
            prefix: Filename prefix
            
        Returns:
            Path to generated CSV file
        """
        filename = self.output_dir / f"{prefix}_summary.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Rok',
                'Liczba_Transakcji',
                'Przychód_PLN',
                'Koszt_PLN',
                'Opłaty_PLN',
                'Razem_Koszt',
                'Dochód_Strata',
                'Strata_z_Poprzedniego_Roku',
                'Dochód_Do_Opodatkowania',
                'Podatek_19_Procent',
            ])
            
            # Summary rows for each year
            for year in sorted(report.years.keys()):
                ty = report.years[year]
                
                net_income = ty.total_revenue_pln - ty.total_cost_with_fees
                
                writer.writerow([
                    year,
                    ty.transaction_count,
                    f"{ty.total_revenue_pln:.2f}",
                    f"{ty.total_costs_pln:.2f}",
                    f"{ty.total_fees_pln:.2f}",
                    f"{ty.total_cost_with_fees:.2f}",
                    f"{net_income:.2f}",
                    f"{ty.loss_from_previous_years:.2f}",
                    f"{ty.taxable_income:.2f}",
                    f"{ty.tax_due_19_percent:.2f}",
                ])
        
        logger.info(f"Summary CSV generated: {filename}")
        return filename
    
    def generate_json(
        self,
        report: TaxReport,
        prefix: str = "tax_report",
    ) -> Path:
        """
        Generate complete report in JSON format.
        
        Includes:
        - Year-by-year summaries
        - Transaction details
        - Exchange rates used
        
        Args:
            report: TaxReport
            prefix: Filename prefix
            
        Returns:
            Path to generated JSON file
        """
        filename = self.output_dir / f"{prefix}.json"
        
        # Build JSON structure
        data = {
            "report_date": report.report_date.isoformat(),
            "summary": report.get_multi_year_summary(),
            "years": {},
            "transactions": [],
        }
        
        # Year summaries
        for year in sorted(report.years.keys()):
            ty = report.years[year]
            data["years"][str(year)] = {
                "total_costs_pln": float(ty.total_costs_pln),
                "total_revenue_pln": float(ty.total_revenue_pln),
                "total_fees_pln": float(ty.total_fees_pln),
                "total_cost_with_fees": float(ty.total_cost_with_fees),
                "taxable_income": float(ty.taxable_income),
                "loss": float(ty.loss),
                "tax_due_19_percent": float(ty.tax_due_19_percent),
                "transaction_count": ty.transaction_count,
                "loss_from_previous_years": float(ty.loss_from_previous_years),
            }
        
        # Transaction details
        for txn in report.transactions:
            data["transactions"].append({
                "timestamp": txn.timestamp.isoformat(),
                "operation": txn.operation_type.value,
                "asset": txn.asset,
                "amount": float(txn.amount),
                "tax_event_type": txn.tax_event_type.value,
                "currency": txn.currency,
                "pln_value": float(txn.pln_value) if txn.pln_value else None,
                "exchange_rate": float(txn.exchange_rate) if txn.exchange_rate else None,
            })
        
        # Write JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"JSON export generated: {filename}")
        return filename
    
    def generate_text_summary(
        self,
        report: TaxReport,
        prefix: str = "tax_report",
    ) -> Path:
        """
        Generate human-readable text summary.
        
        Args:
            report: TaxReport
            prefix: Filename prefix
            
        Returns:
            Path to generated text file
        """
        filename = self.output_dir / f"{prefix}_summary.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("RAPORT PODATKOWY - KRYPTOWALUTY (PIT-38)\n")
            f.write("=" * 70 + "\n\n")
            
            f.write(f"Data raportu: {report.report_date.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Liczba transakcji: {len(report.transactions)}\n\n")
            
            # Multi-year summary
            summary = report.get_multi_year_summary()
            f.write("PODSUMOWANIE WIELOLETNIE:\n")
            f.write("-" * 70 + "\n")
            f.write(f"Całkowity przychód:        {summary['total_revenue_pln']:>15,.2f} PLN\n")
            f.write(f"Całkowity koszt:          {summary['total_costs_pln']:>15,.2f} PLN\n")
            f.write(f"Całkowite opłaty:         {summary['total_fees_pln']:>15,.2f} PLN\n")
            f.write(f"Całkowity dochód podatkowy: {summary['total_taxable_income']:>13,.2f} PLN\n")
            f.write(f"Całkowity podatek (19%):  {summary['total_tax_due']:>15,.2f} PLN\n\n")
            
            # Year-by-year breakdown
            f.write("SZCZEGÓŁOWY PODZIAŁ ROK PO ROKU:\n")
            f.write("=" * 70 + "\n\n")
            
            for year in sorted(report.years.keys()):
                ty = report.years[year]
                
                f.write(f"ROK {year}:\n")
                f.write("-" * 70 + "\n")
                f.write(f"  Liczba transakcji:       {ty.transaction_count:>15}\n")
                f.write(f"  Przychód:                {ty.total_revenue_pln:>15,.2f} PLN\n")
                f.write(f"  Koszt:                   {ty.total_costs_pln:>15,.2f} PLN\n")
                f.write(f"  Opłaty:                  {ty.total_fees_pln:>15,.2f} PLN\n")
                f.write(f"  Razem koszt:             {ty.total_cost_with_fees:>15,.2f} PLN\n")
                
                net_income = ty.total_revenue_pln - ty.total_cost_with_fees
                f.write(f"  Dochód netto:            {net_income:>15,.2f} PLN\n")
                
                if ty.loss_from_previous_years > 0:
                    f.write(f"  Strata z lat poprzednich: {ty.loss_from_previous_years:>15,.2f} PLN\n")
                
                f.write(f"  Dochód do opodatkowania: {ty.taxable_income:>15,.2f} PLN\n")
                f.write(f"  Podatek (19%):           {ty.tax_due_19_percent:>15,.2f} PLN\n")
                
                if ty.loss > 0:
                    f.write(f"  Strata do przeniesienia: {ty.loss:>15,.2f} PLN\n")
                
                f.write("\n")
            
            f.write("=" * 70 + "\n")
            f.write("UWAGI:\n")
            f.write("-" * 70 + "\n")
            f.write("- Wszystkie wartości w PLN\n")
            f.write("- Kursy walut z NBP (dzień poprzedni - T-1)\n")
            f.write("- Stawka podatku: 19% (PIT)\n")
            f.write("- Straty mogą być przeniesione na lata następne\n")
            f.write("- Roczne limity odliczeń nie są uwzględniane\n")
            f.write("\n")
            f.write("ZASTRZEŻENIE:\n")
            f.write("-" * 70 + "\n")
            f.write("Niniejszy raport ma charakter poglądowy. Nie stanowi porady\n")
            f.write("podatkowej. Przed złożeniem PIT-38 skonsultuj się z\n")
            f.write("doradcą podatkowym lub biegłym rewidentem.\n")
            f.write("=" * 70 + "\n")
        
        logger.info(f"Text summary generated: {filename}")
        return filename
    
    def print_summary(self, report: TaxReport) -> None:
        """
        Print summary to console.
        
        Args:
            report: TaxReport to display
        """
        summary = report.get_multi_year_summary()
        
        print("\n" + "=" * 70)
        print("PODSUMOWANIE PODATKOWE - KRYPTOWALUTY (PIT-38)")
        print("=" * 70)
        print(f"\nRok raportu: {datetime.now().year}")
        print(f"Liczba transakcji: {summary['transaction_count']}")
        print(f"Lata obejmujące: {', '.join(str(y) for y in summary['years_covered'])}")
        print("\n" + "-" * 70)
        print(f"Całkowity przychód:      {summary['total_revenue_pln']:>15,.2f} PLN")
        print(f"Całkowity koszt:         {summary['total_costs_pln']:>15,.2f} PLN")
        print(f"Całkowite opłaty:        {summary['total_fees_pln']:>15,.2f} PLN")
        print(f"Dochód podatkowy:        {summary['total_taxable_income']:>15,.2f} PLN")
        print(f"Podatek (19%):           {summary['total_tax_due']:>15,.2f} PLN")
        print("=" * 70 + "\n")
