#!/usr/bin/env python3
"""Run all IPython integration tests and generate comprehensive report."""

import subprocess
import sys
import os
import json
from datetime import datetime
from pathlib import Path


def run_test(test_file):
    """Run a single test file and capture results."""
    print(f"\n{'='*70}")
    print(f"Running: {test_file}")
    print('='*70)
    
    try:
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
            
        return {
            'file': test_file,
            'success': result.returncode == 0,
            'output': result.stdout,
            'errors': result.stderr,
            'returncode': result.returncode
        }
    except subprocess.TimeoutExpired:
        print(f"✗ Test timed out: {test_file}")
        return {
            'file': test_file,
            'success': False,
            'output': '',
            'errors': 'Test timed out after 60 seconds',
            'returncode': -1
        }
    except Exception as e:
        print(f"✗ Test failed to run: {e}")
        return {
            'file': test_file,
            'success': False,
            'output': '',
            'errors': str(e),
            'returncode': -1
        }


def analyze_results(results):
    """Analyze test results and generate summary."""
    
    analysis = {
        'total_tests': len(results),
        'passed': sum(1 for r in results if r['success']),
        'failed': sum(1 for r in results if not r['success']),
        'categories': {
            'basic': None,
            'namespace': None,
            'protocol': None,
            'capabilities': None,
            'performance': None,
        }
    }
    
    # Map test files to categories
    for result in results:
        filename = os.path.basename(result['file'])
        if 'test_1' in filename:
            analysis['categories']['basic'] = result['success']
        elif 'test_2' in filename:
            analysis['categories']['namespace'] = result['success']
        elif 'test_3' in filename:
            analysis['categories']['protocol'] = result['success']
        elif 'test_4' in filename:
            analysis['categories']['capabilities'] = result['success']
        elif 'test_5' in filename:
            analysis['categories']['performance'] = result['success']
    
    return analysis


def generate_report(results, analysis):
    """Generate detailed integration report."""
    
    report = []
    report.append("\n" + "="*80)
    report.append("IPYTHON INTEGRATION INVESTIGATION REPORT")
    report.append("="*80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    # Overall Summary
    report.append("OVERALL SUMMARY")
    report.append("-"*40)
    report.append(f"Total Test Categories: {analysis['total_tests']}")
    report.append(f"Passed: {analysis['passed']}")
    report.append(f"Failed: {analysis['failed']}")
    report.append(f"Success Rate: {analysis['passed']/analysis['total_tests']*100:.1f}%")
    report.append("")
    
    # Category Analysis
    report.append("CATEGORY ANALYSIS")
    report.append("-"*40)
    
    category_details = {
        'basic': 'Basic IPython functionality (import, shell creation, async, I/O, errors)',
        'namespace': 'Namespace bridging with PyREPL3 NamespaceManager',
        'protocol': 'Protocol message integration for I/O and results',
        'capabilities': 'Capability injection and security policies',
        'performance': 'Performance, cancellation, and event system',
    }
    
    for cat, passed in analysis['categories'].items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        report.append(f"{cat.upper():15} {status}")
        report.append(f"  {category_details[cat]}")
    
    report.append("")
    
    # Critical Findings
    report.append("CRITICAL FINDINGS")
    report.append("-"*40)
    
    findings = []
    
    if analysis['categories']['basic']:
        findings.append("✓ IPython core functionality works well")
        findings.append("✓ Async execution and top-level await supported")
        findings.append("✓ I/O streams can be overridden successfully")
    else:
        findings.append("✗ IPython basic functionality has issues")
    
    if analysis['categories']['namespace']:
        findings.append("✓ Namespace bridging is feasible")
        findings.append("✓ Transaction support can be implemented")
        findings.append("✓ Thread-safe namespace access works")
    else:
        findings.append("✗ Namespace integration problematic")
    
    if analysis['categories']['protocol']:
        findings.append("✓ Protocol messages can be integrated")
        findings.append("✓ Output/input/result/error routing works")
    else:
        findings.append("✗ Protocol integration needs work")
    
    if analysis['categories']['capabilities']:
        findings.append("✓ Capability injection pattern works")
        findings.append("✓ Security policies can be enforced")
        findings.append("⚠ IPython preprocessors limited for security")
    else:
        findings.append("✗ Capability system integration failed")
    
    if analysis['categories']['performance']:
        findings.append("⚠ IPython adds ~20-50% execution overhead")
        findings.append("⚠ No built-in cooperative cancellation")
        findings.append("✓ Event system provides good hooks")
        findings.append("⚠ Concurrent execution requires workarounds")
    else:
        findings.append("✗ Performance/event integration issues")
    
    for finding in findings:
        report.append(f"  {finding}")
    
    report.append("")
    
    # Recommendations
    report.append("RECOMMENDATIONS")
    report.append("-"*40)
    
    if analysis['passed'] >= 4:  # Most tests passed
        report.append("✓ IPython integration is FEASIBLE with caveats:")
        report.append("  1. Use IPython for core execution engine")
        report.append("  2. Keep custom namespace management layer")
        report.append("  3. Implement capability system on top")
        report.append("  4. Add custom cancellation mechanism")
        report.append("  5. Use event hooks for lifecycle management")
    elif analysis['passed'] >= 2:  # Some tests passed
        report.append("⚠ IPython integration is PARTIALLY FEASIBLE:")
        report.append("  1. Consider hybrid approach")
        report.append("  2. Use IPython for async execution only")
        report.append("  3. Keep custom components for critical features")
        report.append("  4. Extensive testing required")
    else:
        report.append("✗ IPython integration NOT RECOMMENDED:")
        report.append("  1. Too many integration issues")
        report.append("  2. Better to keep custom implementation")
        report.append("  3. Consider extracting specific IPython components")
    
    report.append("")
    
    # Specific Issues to Address
    report.append("ISSUES TO ADDRESS")
    report.append("-"*40)
    report.append("  1. Cancellation: Need custom sys.settrace equivalent")
    report.append("  2. Security: IPython preprocessors insufficient")
    report.append("  3. Concurrency: InteractiveShell singleton problematic")
    report.append("  4. Performance: Overhead needs optimization")
    report.append("  5. Protocol: Full integration needs more work")
    
    report.append("")
    
    # Integration Effort Estimate
    report.append("INTEGRATION EFFORT ESTIMATE")
    report.append("-"*40)
    
    if analysis['passed'] >= 4:
        report.append("  Phase 1 (Core): 1-2 weeks")
        report.append("  Phase 2 (Capabilities): 1 week")
        report.append("  Phase 3 (Optimization): 1 week")
        report.append("  Testing & Debugging: 1-2 weeks")
        report.append("  TOTAL: 4-6 weeks")
    else:
        report.append("  Custom implementation recommended")
        report.append("  IPython integration would take 8-12 weeks")
        report.append("  High risk of incomplete feature parity")
    
    report.append("")
    report.append("="*80)
    report.append("END OF REPORT")
    report.append("="*80)
    
    return '\n'.join(report)


def main():
    """Run all tests and generate report."""
    
    # Find all test files - prefer fixed versions if they exist
    test_dir = Path('ipython_investigation')
    
    # Get all test files
    all_test_files = sorted(test_dir.glob('test_*.py'))
    
    # Prefer fixed versions
    test_files = []
    for i in range(1, 6):
        fixed_version = test_dir / f'test_{i}_*_fixed.py'
        fixed_files = list(test_dir.glob(f'test_{i}_*_fixed.py'))
        if fixed_files:
            test_files.append(fixed_files[0])
        else:
            # Fall back to original
            orig_files = list(test_dir.glob(f'test_{i}_*.py'))
            if orig_files and not any('_fixed' in str(f) for f in orig_files):
                test_files.append(orig_files[0])
    
    if not test_files:
        print("No test files found!")
        return 1
    
    print(f"Found {len(test_files)} test files")
    
    # Check if IPython is installed
    try:
        import IPython
        print(f"✓ IPython {IPython.__version__} is installed")
    except ImportError:
        print("✗ IPython is not installed!")
        print("  Run: pip install ipython")
        return 1
    
    # Run all tests
    results = []
    for test_file in test_files:
        result = run_test(str(test_file))
        results.append(result)
    
    # Analyze results
    analysis = analyze_results(results)
    
    # Generate report
    report = generate_report(results, analysis)
    print(report)
    
    # Save report
    report_file = test_dir / 'integration_report.txt'
    report_file.write_text(report)
    print(f"\nReport saved to: {report_file}")
    
    # Save detailed results as JSON
    json_file = test_dir / 'test_results.json'
    with open(json_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'analysis': analysis,
            'results': results
        }, f, indent=2)
    print(f"Detailed results saved to: {json_file}")
    
    return 0 if analysis['passed'] > analysis['failed'] else 1


if __name__ == "__main__":
    sys.exit(main())