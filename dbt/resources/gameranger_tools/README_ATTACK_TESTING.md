# 🔥 Advanced Session Attack Framework - Complete Testing Guide

## System Requirements

- Python 3.7+
- Windows/Linux/Mac
- 3 terminal windows (or tabs)

## File Overview

| File | Purpose |
|------|---------|
| `continuous_protocol_test.py` | 🔍 Server that receives packets and analyzes them |
| `aggressive_session_attack.py` | ⚔️ Attacks server with different vectors |
| `attack_monitor.py` | 📊 Collects detailed statistics during attacks |
| `analyze_data.py` | 📈 Analyzes collected data and generates report |
| `analyze_attacks.py` | 🎯 Orchestrates entire test suite |

## Quick Start - Comprehensive Testing

### Step 1: Terminal 1 - Start Server
```bash
python continuous_protocol_test.py
```
This will listen on `127.0.0.1:16000` and display:
- Real-time packet count
- Valid vs invalid packets
- Sequence violations
- Anomalies detected
- Bandwidth usage

### Step 2: Terminal 2 - Start Monitor
```bash
python attack_monitor.py
```
This collects fine-grained statistics:
- Saves to `attack_stats.jsonl`
- Tracks each snapshot
- Records anomalies

### Step 3: Terminal 3 - Run Analysis
```bash
python analyze_data.py
```
After you run attacks, this analyzes the data and generates:
- `ATTACK_ANALYSIS_FINAL.txt` - comprehensive report
- Statistics breakdown
- Effectiveness ranking
- Thesis conclusions

---

## Testing Individual Attacks

Run these in Terminal 3 (one at a time, wait for completion):

### 1. Session Exhaustion Attack
```bash
python aggressive_session_attack.py --attack session_exhaustion --duration 60 --workers 4 --yes
```
**Effect**: Creates new sessions rapidly, exhausts memory pool

### 2. Replay Attack
```bash
python aggressive_session_attack.py --attack replay --duration 60 --workers 4 --yes
```
**Effect**: Repeats same valid packets multiple times

### 3. Token Brute Force
```bash
python aggressive_session_attack.py --attack token_bruteforce --duration 60 --workers 4 --yes
```
**Effect**: Attempts to guess valid tokens

### 4. State Confusion
```bash
python aggressive_session_attack.py --attack state_confusion --duration 60 --workers 4 --yes
```
**Effect**: Sends packets in wrong order, wrong sequence numbers

### 5. Slowloris DoS
```bash
python aggressive_session_attack.py --attack slowloris --duration 60 --workers 4 --yes
```
**Effect**: Keeps many sessions alive with heartbeat, drains resources

### 6. Connection Reset
```bash
python aggressive_session_attack.py --attack connection_reset --duration 60 --workers 4 --yes
```
**Effect**: Floods fake DISCONNECT packets

### 7. Heartbeat Suppression
```bash
python aggressive_session_attack.py --attack heartbeat_suppression --duration 60 --workers 4 --yes
```
**Effect**: Maintains zombie sessions

### 8. Combined Attack (All at once!)
```bash
python aggressive_session_attack.py --attack combined --duration 120 --workers 8 --yes
```
**Effect**: Chaos - all attacks simultaneously

---

## What to Observe

### On Server Terminal (continuous_protocol_test.py):

Watch these metrics in real-time:

```
📦 Total packets: 47,755,057        ← Total packets processed
🔄 Current PPS: 146,350 packets/sec ← Packets per second
📊 Bandwidth: 79.06 Mbps            ← Network usage
✅ Valid sessions: 42,027,486       ← JSON with token/session_id
❌ Invalid packets: 4,985,132       ← Raw/malformed packets
⚠️  Anomalies detected: 0           ← Protocol violations
🚨 Sequence violations: 742,439     ← Out-of-order sequences
```

### Expected Results by Attack:

| Attack | Valid Sessions ↑ | Invalid ↑ | Seq Violations ↑ |
|--------|------------------|-----------|------------------|
| session_exhaustion | 🔴 HIGH | 🟡 Medium | 🟢 Low |
| replay | 🔴 HIGH | 🟡 Medium | 🔴 HIGH |
| token_bruteforce | 🟡 Medium | 🔴 HIGH | 🟡 Medium |
| state_confusion | 🟡 Medium | 🟡 Medium | 🔴 HIGH |
| slowloris | 🟡 Medium | 🟡 Medium | 🟡 Medium |
| connection_reset | 🟡 Medium | 🟡 Medium | 🟡 Medium |
| heartbeat_suppression | 🟡 Medium | 🟡 Medium | 🟡 Medium |
| combined | 🔴 HIGH | 🔴 HIGH | 🔴 HIGH |

---

## Analysis & Report Generation

After running attacks, analyze the data:

```bash
# Analyze collected statistics
python analyze_data.py
```

This generates: `ATTACK_ANALYSIS_FINAL.txt`

Report includes:
- ✅ Overview statistics
- ✅ Packet breakdown
- ✅ Attack effectiveness ranking
- ✅ Layer-7 vs Layer-3 comparison
- ✅ Mitigation recommendations
- ✅ Academic conclusions

---

## Key Findings

### Layer-7 > Layer-3

| Aspect | Raw UDP Flood | Session Attacks |
|--------|---------------|-----------------|
| PPS | ~70k | ~146k |
| Damage | ❌ NONE | ✅ HIGH |
| Visibility | Blocked | Processed |
| Sophistication | Trivial | Advanced |

### Attack Effectiveness

```
Raw UDP Flood:
- 140M+ packets sent
- 0 valid sessions created
- 0 damage to application
- Reason: No Layer-7 state

Session Attacks:
- 47M+ packets sent
- 42M+ valid sessions
- HIGH impact on server
- Reason: Mimics real protocol
```

---

## For Your Thesis

### Use This Data For:

1. **Chapter 4-5**: Protocol Design
   - Show Layer-7 security importance
   - Demonstrate real attack vectors
   - Compare different attacks

2. **Attack Analysis**:
   - 8 different Layer-7 attacks
   - Measurable impact metrics
   - Empirical results

3. **Security Recommendations**:
   - Rate limiting strategies
   - Session validation
   - Token hardening
   - Anomaly detection

4. **Conclusions**:
   - Layer-7 is critical
   - State machines need protection
   - Multi-layered defense necessary

---

## Troubleshooting

### Monitor showing 0 packets?
- Make sure `continuous_protocol_test.py` is running first
- Check firewall isn't blocking localhost:16000
- Try `netstat -an | grep 16000` to verify port listening

### Attack not sending packets?
- Check Windows Firewall (may block UDP)
- Try with `--yes` flag to skip confirmation
- Verify `aggressive_session_attack.py` is in same directory

### No data in attack_stats.jsonl?
- Make sure `attack_monitor.py` was running during attack
- Check file permissions
- Look for error messages in attack_monitor terminal

### Report won't generate?
- Make sure `attack_stats.jsonl` exists
- Run `python analyze_data.py` with monitor still running
- Check `attack_stats.jsonl` has content: `cat attack_stats.jsonl | head`

---

## Advanced Usage

### Custom Duration & Workers

```bash
# Longer test (180 seconds, 8 workers)
python aggressive_session_attack.py --attack session_exhaustion --duration 180 --workers 8 --yes

# Stealth test (low PPS)
python aggressive_session_attack.py --attack slowloris --duration 300 --workers 1 --yes

# High performance test
python aggressive_session_attack.py --attack combined --duration 60 --workers 8 --yes
```

### Multiple Attacks in Sequence

```bash
for attack in session_exhaustion replay token_bruteforce; do
    echo "Testing $attack..."
    python aggressive_session_attack.py --attack $attack --duration 30 --workers 4 --yes
    sleep 5
done
python analyze_data.py
```

---

## Expected Output Files

After testing:

```
📁 /dbt/resources/gameranger_tools/
  ├─ attack_stats.jsonl           (Statistics from monitor)
  ├─ ATTACK_ANALYSIS_FINAL.txt   (Generated report)
  ├─ *.py                         (Scripts)
```

---

## Questions?

Use this framework to answer in your thesis:

✅ "Which Layer-7 attacks are most effective?"
✅ "How does protocol design impact security?"
✅ "What metrics show attack impact?"
✅ "How to defend against these attacks?"
✅ "What's the difference between Layer-3 and Layer-7 security?"

---

**Good luck with your thesis! This framework provides empirical evidence for sophisticated Layer-7 attacks.** 🚀
