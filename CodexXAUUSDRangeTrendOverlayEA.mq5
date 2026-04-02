#property strict
#property version   "1.00"
#property description "XAUUSD range-fade core EA with trend-day breakout overlay."
#property description "Range logic is based on the best time-asymmetry configuration; trend days use a selective breakout overlay."

#include <Trade/Trade.mqh>

input long   InpMagicNumber             = 20260328;
input double InpUnitLots                = 0.10;
input int    InpSessionStartHour        = 6;
input int    InpSessionEndHour          = 22;
input int    InpEntryStartHour          = 8;
input int    InpEntryEndHour            = 16;
input int    InpRangeBars               = 4;
input int    InpATRPeriod               = 14;
input double InpRangeStepATR            = 0.75;
input double InpLongEntryATR            = 1.30;
input double InpShortEntryATR           = 0.90;
input double InpLongStopATR             = 1.75;
input double InpShortStopATR            = 1.75;
input int    InpLongMaxUnits            = 2;
input int    InpShortMaxUnits           = 2;
input int    InpRegimeADXPeriod         = 14;
input double InpRegimeADXThreshold      = 22.0;
input int    InpRegimeEMAPeriod         = 20;
input int    InpDeviationPoints         = 10;

input double InpOverlayTrendADXMin      = 34.0;
input int    InpOverlayLookbackBars     = 24;
input double InpOverlayBreakoutBufferATR= 0.10;
input double InpOverlayStopATR          = 1.20;
input double InpOverlayTargetR          = 2.00;
input int    InpOverlayMaxHoldBars      = 10;
input double InpOverlayBreakevenR       = 0.80;
input double InpOverlayTrailTriggerR    = 0.80;
input double InpOverlayTrailATR         = 0.80;
input bool   InpVerboseLogs             = true;

CTrade   g_trade;
int      g_atr_handle      = INVALID_HANDLE;
int      g_adx_d1_handle   = INVALID_HANDLE;
int      g_ema_d1_handle   = INVALID_HANDLE;
datetime g_last_bar_time   = 0;

bool     g_overlay_active  = false;
int      g_overlay_side    = 0;
double   g_overlay_entry   = 0.0;
double   g_overlay_stopdist= 0.0;
double   g_overlay_favext  = 0.0;
datetime g_overlay_bar_time= 0;


double NormalizeVolume(const double volume)
{
   double min_volume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_volume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step       = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0 || volume <= 0.0)
      return 0.0;

   double normalized = MathRound(volume / step) * step;
   normalized = MathMax(min_volume, MathMin(max_volume, normalized));
   int digits = 0;
   double probe = step;
   while(digits < 8 && MathAbs(MathRound(probe) - probe) > 1e-8)
   {
      probe *= 10.0;
      digits++;
   }
   return NormalizeDouble(normalized, digits);
}


bool IsNewBar()
{
   datetime current_bar = iTime(_Symbol, PERIOD_M15, 0);
   if(current_bar == 0)
      return false;
   if(current_bar != g_last_bar_time)
   {
      g_last_bar_time = current_bar;
      return true;
   }
   return false;
}


datetime SessionStartTime(const datetime bar_time)
{
   MqlDateTime dt;
   TimeToStruct(bar_time, dt);
   dt.hour = 0;
   dt.min  = 0;
   dt.sec  = 0;
   return StructToTime(dt) + InpSessionStartHour * 3600;
}


datetime SessionEndTime(const datetime bar_time)
{
   MqlDateTime dt;
   TimeToStruct(bar_time, dt);
   dt.hour = 0;
   dt.min  = 0;
   dt.sec  = 0;
   return StructToTime(dt) + InpSessionEndHour * 3600;
}


bool CopyOpeningRange(const datetime signal_bar_time, double &range_high, double &range_low)
{
   datetime session_start = SessionStartTime(signal_bar_time);
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int copied = CopyRates(_Symbol, PERIOD_M15, session_start, InpRangeBars, rates);
   if(copied != InpRangeBars || rates[0].time != session_start)
      return false;

   range_high = rates[0].high;
   range_low  = rates[0].low;
   for(int i = 1; i < copied; ++i)
   {
      range_high = MathMax(range_high, rates[i].high);
      range_low  = MathMin(range_low, rates[i].low);
   }
   return true;
}


bool GetDailyRegime(bool &is_trend_day, int &bias, double &adx_value)
{
   is_trend_day = false;
   bias         = 0;
   adx_value    = 0.0;

   double adx_buf[];
   double ema_buf[];
   double close_buf[];
   ArraySetAsSeries(adx_buf, true);
   ArraySetAsSeries(ema_buf, true);
   ArraySetAsSeries(close_buf, true);

   if(CopyBuffer(g_adx_d1_handle, 0, 1, 1, adx_buf) != 1)
      return false;
   if(CopyBuffer(g_ema_d1_handle, 0, 1, 1, ema_buf) != 1)
      return false;
   if(CopyClose(_Symbol, PERIOD_D1, 1, 1, close_buf) != 1)
      return false;

   adx_value = adx_buf[0];
   if(close_buf[0] > ema_buf[0])
      bias = 1;
   else if(close_buf[0] < ema_buf[0])
      bias = -1;
   is_trend_day = (bias != 0 && adx_value >= InpRegimeADXThreshold);
   return true;
}


int CurrentExposureUnits(bool &mixed, int &side, double &volume)
{
   mixed  = false;
   side   = 0;
   volume = 0.0;
   double long_volume = 0.0;
   double short_volume = 0.0;

   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      ENUM_POSITION_TYPE pos_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double pos_volume = PositionGetDouble(POSITION_VOLUME);
      if(pos_type == POSITION_TYPE_BUY)
         long_volume += pos_volume;
      else if(pos_type == POSITION_TYPE_SELL)
         short_volume += pos_volume;
   }

   mixed = (long_volume > 0.0 && short_volume > 0.0);
   if(long_volume > 0.0 && short_volume <= 0.0)
   {
      side = 1;
      volume = long_volume;
   }
   else if(short_volume > 0.0 && long_volume <= 0.0)
   {
      side = -1;
      volume = short_volume;
   }

   if(InpUnitLots <= 0.0)
      return 0;
   return (int)MathRound(volume / InpUnitLots) * side;
}


bool CloseManagedPositions()
{
   bool ok = true;
   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;
      if(!g_trade.PositionClose(ticket))
      {
         ok = false;
         PrintFormat("Failed to close ticket %I64u. Retcode=%d", ticket, g_trade.ResultRetcode());
      }
   }
   return ok;
}


bool ReduceExposure(const int side, double volume_to_reduce)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double remaining = volume_to_reduce;
   for(int i = PositionsTotal() - 1; i >= 0 && remaining > step / 2.0; --i)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      ENUM_POSITION_TYPE pos_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      if((side > 0 && pos_type != POSITION_TYPE_BUY) || (side < 0 && pos_type != POSITION_TYPE_SELL))
         continue;

      double pos_volume = PositionGetDouble(POSITION_VOLUME);
      double close_volume = NormalizeVolume(MathMin(pos_volume, remaining));
      if(close_volume <= 0.0)
         continue;

      bool closed = false;
      if(MathAbs(close_volume - pos_volume) <= step / 2.0)
         closed = g_trade.PositionClose(ticket);
      else
         closed = g_trade.PositionClosePartial(ticket, close_volume);

      if(!closed)
         return false;
      remaining -= close_volume;
   }
   return (remaining <= step / 2.0);
}


bool AddExposure(const int side, const double volume_to_add)
{
   double volume = NormalizeVolume(volume_to_add);
   if(volume <= 0.0)
      return true;
   bool ok = (side > 0) ? g_trade.Buy(volume, _Symbol) : g_trade.Sell(volume, _Symbol);
   return ok;
}


int ApplyEntryTimeFilter(const int target_units, const int current_units, const datetime next_open_time, string &reason)
{
   MqlDateTime dt;
   TimeToStruct(next_open_time, dt);
   if(InpEntryStartHour <= dt.hour && dt.hour < InpEntryEndHour)
      return target_units;
   if(current_units == 0)
   {
      reason = "time_skip";
      return 0;
   }
   if(target_units == 0)
      return 0;
   int target_side = (target_units > 0) ? 1 : -1;
   int current_side = (current_units > 0) ? 1 : -1;
   if(target_side != current_side)
   {
      reason = "time_no_reverse";
      return 0;
   }
   if(MathAbs(target_units) > MathAbs(current_units))
   {
      reason = "time_no_add";
      return current_units;
   }
   return target_units;
}


bool AdjustToTargetUnits(const int target_units)
{
   bool mixed = false;
   int current_side = 0;
   double current_volume = 0.0;
   CurrentExposureUnits(mixed, current_side, current_volume);

   if(mixed)
   {
      if(!CloseManagedPositions())
         return false;
      current_side = 0;
      current_volume = 0.0;
   }

   int target_side = 0;
   if(target_units > 0)
      target_side = 1;
   else if(target_units < 0)
      target_side = -1;

   double target_volume = NormalizeVolume(MathAbs(target_units) * InpUnitLots);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(target_volume <= 0.0)
      return CloseManagedPositions();

   if(current_side != 0 && current_side != target_side)
   {
      if(!CloseManagedPositions())
         return false;
      current_side = 0;
      current_volume = 0.0;
   }

   double diff = target_volume - current_volume;
   if(MathAbs(diff) <= step / 2.0)
      return true;
   if(diff > 0.0)
      return AddExposure(target_side, diff);
   return ReduceExposure(target_side, -diff);
}


int ComputeRangeTargetUnits(string &reason)
{
   reason = "flat";
   datetime signal_bar_time = iTime(_Symbol, PERIOD_M15, 1);
   if(signal_bar_time == 0)
   {
      reason = "missing_bar";
      return 0;
   }

   int tf_seconds = PeriodSeconds(PERIOD_M15);
   datetime session_start = SessionStartTime(signal_bar_time);
   datetime session_end = SessionEndTime(signal_bar_time);
   datetime next_open_time = iTime(_Symbol, PERIOD_M15, 0);

   if(signal_bar_time < session_start)
   {
      reason = "before_session";
      return 0;
   }
   if(signal_bar_time >= session_end - tf_seconds)
   {
      reason = "session_end";
      return 0;
   }
   if(signal_bar_time < session_start + InpRangeBars * tf_seconds)
   {
      reason = "opening_range_build";
      return 0;
   }

   bool is_trend_day = false;
   int bias = 0;
   double adx_value = 0.0;
   if(!GetDailyRegime(is_trend_day, bias, adx_value))
   {
      reason = "regime_data_missing";
      return 0;
   }
   if(is_trend_day)
   {
      reason = "trend_skip";
      return 0;
   }

   double range_high = 0.0;
   double range_low = 0.0;
   if(!CopyOpeningRange(signal_bar_time, range_high, range_low))
   {
      reason = "opening_range_missing";
      return 0;
   }

   double atr_buf[];
   double close_buf[];
   ArraySetAsSeries(atr_buf, true);
   ArraySetAsSeries(close_buf, true);
   if(CopyBuffer(g_atr_handle, 0, 1, 1, atr_buf) != 1 || CopyClose(_Symbol, PERIOD_M15, 1, 1, close_buf) != 1)
   {
      reason = "data_missing";
      return 0;
   }
   double atr_value = atr_buf[0];
   double close_value = close_buf[0];
   if(atr_value <= 0.0)
   {
      reason = "atr_invalid";
      return 0;
   }

   double range_mid = 0.5 * (range_high + range_low);
   double deviation = (close_value - range_mid) / atr_value;
   double abs_dev = MathAbs(deviation);
   int target_side = (deviation > 0.0) ? -1 : 1;
   double entry_atr = (target_side > 0) ? InpLongEntryATR : InpShortEntryATR;
   double stop_atr = (target_side > 0) ? InpLongStopATR : InpShortStopATR;
   int max_units = (target_side > 0) ? InpLongMaxUnits : InpShortMaxUnits;

   if(target_side > 0 && close_value < range_low - stop_atr * atr_value)
   {
      reason = "range_stop";
      return 0;
   }
   if(target_side < 0 && close_value > range_high + stop_atr * atr_value)
   {
      reason = "range_stop";
      return 0;
   }
   if(abs_dev < entry_atr)
   {
      reason = "range_flat";
      return 0;
   }

   int units = (int)MathFloor((abs_dev - entry_atr) / InpRangeStepATR) + 1;
   units = MathMax(1, MathMin(max_units, units));
   int target_units = target_side * units;

   bool mixed = false;
   int current_side = 0;
   double current_volume = 0.0;
   int current_units = CurrentExposureUnits(mixed, current_side, current_volume);
   if(mixed)
      current_units = 0;
   return ApplyEntryTimeFilter(target_units, current_units, next_open_time, reason);
}


int ComputeOverlaySignal(string &reason, double &atr_value)
{
   reason = "overlay_flat";
   atr_value = 0.0;

   bool is_trend_day = false;
   int bias = 0;
   double adx_value = 0.0;
   if(!GetDailyRegime(is_trend_day, bias, adx_value))
   {
      reason = "overlay_regime_missing";
      return 0;
   }
   if(!is_trend_day || adx_value < InpOverlayTrendADXMin || bias == 0)
   {
      reason = "overlay_no_trend";
      return 0;
   }

   datetime signal_bar_time = iTime(_Symbol, PERIOD_M15, 1);
   if(signal_bar_time == 0)
   {
      reason = "overlay_missing_bar";
      return 0;
   }

   MqlDateTime dt;
   TimeToStruct(signal_bar_time, dt);
   if(dt.hour < InpEntryStartHour || dt.hour >= InpEntryEndHour)
   {
      reason = "overlay_time";
      return 0;
   }

   double atr_buf[];
   ArraySetAsSeries(atr_buf, true);
   if(CopyBuffer(g_atr_handle, 0, 1, 1, atr_buf) != 1)
   {
      reason = "overlay_atr_missing";
      return 0;
   }
   atr_value = atr_buf[0];
   if(atr_value <= 0.0)
   {
      reason = "overlay_atr_invalid";
      return 0;
   }

   MqlRates bars[];
   ArraySetAsSeries(bars, true);
   if(CopyRates(_Symbol, PERIOD_M15, 1, InpOverlayLookbackBars + 2, bars) < InpOverlayLookbackBars + 1)
   {
      reason = "overlay_rates_missing";
      return 0;
   }

   double prior_high = bars[2].high;
   double prior_low  = bars[2].low;
   for(int i = 2; i < InpOverlayLookbackBars + 2; ++i)
   {
      prior_high = MathMax(prior_high, bars[i].high);
      prior_low  = MathMin(prior_low, bars[i].low);
   }

   double close1 = bars[1].close;
   double low1 = bars[1].low;
   double high1 = bars[1].high;
   double loc = 0.5;
   if(high1 > low1)
      loc = (close1 - low1) / (high1 - low1);

   if(bias > 0 && close1 > prior_high + InpOverlayBreakoutBufferATR * atr_value && loc >= 0.65)
   {
      reason = "overlay_breakout_buy";
      return 1;
   }
   if(bias < 0 && close1 < prior_low - InpOverlayBreakoutBufferATR * atr_value && loc <= 0.35)
   {
      reason = "overlay_breakout_sell";
      return -1;
   }

   reason = "overlay_no_break";
   return 0;
}


void ResetOverlayState()
{
   g_overlay_active = false;
   g_overlay_side = 0;
   g_overlay_entry = 0.0;
   g_overlay_stopdist = 0.0;
   g_overlay_favext = 0.0;
   g_overlay_bar_time = 0;
}


bool OpenOverlayTrade(const int side, const double atr_value)
{
   double volume = NormalizeVolume(InpUnitLots);
   if(volume <= 0.0)
      return false;

   double price = (side > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double stop_dist = InpOverlayStopATR * atr_value;
   double sl = (side > 0) ? price - stop_dist : price + stop_dist;
   double tp = (side > 0) ? price + stop_dist * InpOverlayTargetR : price - stop_dist * InpOverlayTargetR;

   bool ok = (side > 0)
             ? g_trade.Buy(volume, _Symbol, price, sl, tp, "overlay_breakout")
             : g_trade.Sell(volume, _Symbol, price, sl, tp, "overlay_breakout");
   if(!ok)
      return false;

   g_overlay_active = true;
   g_overlay_side = side;
   g_overlay_entry = price;
   g_overlay_stopdist = stop_dist;
   g_overlay_favext = price;
   g_overlay_bar_time = iTime(_Symbol, PERIOD_M15, 0);
   return true;
}


void ManageOverlayPosition()
{
   bool mixed = false;
   int side = 0;
   double volume = 0.0;
   int units = CurrentExposureUnits(mixed, side, volume);
   if(mixed || units == 0 || side == 0)
   {
      ResetOverlayState();
      return;
   }

   ulong ticket = 0;
   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      ulong probe = PositionGetTicket(i);
      if(probe == 0 || !PositionSelectByTicket(probe))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;
      ticket = probe;
      break;
   }
   if(ticket == 0 || !PositionSelectByTicket(ticket))
   {
      ResetOverlayState();
      return;
   }

   if(!g_overlay_active)
   {
      g_overlay_active = true;
      g_overlay_side = side;
      g_overlay_entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      g_overlay_stopdist = (side > 0) ? (g_overlay_entry - sl) : (sl - g_overlay_entry);
      g_overlay_favext = g_overlay_entry;
      g_overlay_bar_time = iTime(_Symbol, PERIOD_M15, 0);
   }

   double atr_entry = (InpOverlayStopATR > 0.0) ? (g_overlay_stopdist / InpOverlayStopATR) : 0.0;
   double last_high = iHigh(_Symbol, PERIOD_M15, 1);
   double last_low  = iLow(_Symbol, PERIOD_M15, 1);
   if(g_overlay_side > 0)
      g_overlay_favext = MathMax(g_overlay_favext, last_high);
   else
      g_overlay_favext = MathMin(g_overlay_favext, last_low);

   double current_sl = PositionGetDouble(POSITION_SL);
   double current_tp = PositionGetDouble(POSITION_TP);
   double new_sl = current_sl;

   if(g_overlay_side > 0)
   {
      if(g_overlay_favext - g_overlay_entry >= InpOverlayBreakevenR * g_overlay_stopdist)
         new_sl = MathMax(new_sl, g_overlay_entry);
      if(g_overlay_favext - g_overlay_entry >= InpOverlayTrailTriggerR * g_overlay_stopdist)
         new_sl = MathMax(new_sl, g_overlay_favext - InpOverlayTrailATR * atr_entry);
   }
   else
   {
      if(g_overlay_entry - g_overlay_favext >= InpOverlayBreakevenR * g_overlay_stopdist)
         new_sl = (current_sl == 0.0) ? g_overlay_entry : MathMin(new_sl, g_overlay_entry);
      if(g_overlay_entry - g_overlay_favext >= InpOverlayTrailTriggerR * g_overlay_stopdist)
      {
         double trail_sl = g_overlay_favext + InpOverlayTrailATR * atr_entry;
         new_sl = (current_sl == 0.0) ? trail_sl : MathMin(new_sl, trail_sl);
      }
   }

   if(MathAbs(new_sl - current_sl) > (_Point * 2.0))
      g_trade.PositionModify(ticket, new_sl, current_tp);

   datetime current_bar = iTime(_Symbol, PERIOD_M15, 0);
   int bars_held = (int)((current_bar - g_overlay_bar_time) / PeriodSeconds(PERIOD_M15));
   if(bars_held >= InpOverlayMaxHoldBars || current_bar >= SessionEndTime(current_bar))
   {
      g_trade.PositionClose(ticket);
      ResetOverlayState();
   }
}


int OnInit()
{
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(InpDeviationPoints);
   g_trade.SetTypeFillingBySymbol(_Symbol);

   g_atr_handle    = iATR(_Symbol, PERIOD_M15, InpATRPeriod);
   g_adx_d1_handle = iADX(_Symbol, PERIOD_D1, InpRegimeADXPeriod);
   g_ema_d1_handle = iMA(_Symbol, PERIOD_D1, InpRegimeEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
   if(g_atr_handle == INVALID_HANDLE || g_adx_d1_handle == INVALID_HANDLE || g_ema_d1_handle == INVALID_HANDLE)
      return INIT_FAILED;

   g_last_bar_time = iTime(_Symbol, PERIOD_M15, 0);
   ResetOverlayState();
   return INIT_SUCCEEDED;
}


void OnDeinit(const int reason)
{
   if(g_atr_handle != INVALID_HANDLE)
      IndicatorRelease(g_atr_handle);
   if(g_adx_d1_handle != INVALID_HANDLE)
      IndicatorRelease(g_adx_d1_handle);
   if(g_ema_d1_handle != INVALID_HANDLE)
      IndicatorRelease(g_ema_d1_handle);
}


void OnTick()
{
   if(!IsNewBar())
      return;

   bool is_trend_day = false;
   int bias = 0;
   double adx_value = 0.0;
   if(!GetDailyRegime(is_trend_day, bias, adx_value))
      return;

   if(is_trend_day)
   {
      if(!g_overlay_active)
      {
         string overlay_reason = "";
         double atr_value = 0.0;
         int side = ComputeOverlaySignal(overlay_reason, atr_value);
         if(side != 0)
         {
            CloseManagedPositions();
            OpenOverlayTrade(side, atr_value);
         }
      }
      else
      {
         ManageOverlayPosition();
      }
      return;
   }

   if(g_overlay_active)
   {
      CloseManagedPositions();
      ResetOverlayState();
   }

   string range_reason = "";
   int target_units = ComputeRangeTargetUnits(range_reason);
   AdjustToTargetUnits(target_units);
}
