;+
; NAME:
;   giro_es_statistics.pro
;
; PURPOSE:
;   オーストラリアのイオノゾンデ(Digisonde)から得られる foEs (スポラディックE層
;   臨界周波数) のデータを GIRO/DIDBase からダウンロードし、月×地方時ごとの
;   スポラディックE発生頻度(%)を統計的に求めて図示する。
;
; DATA SOURCE:
;   Global Ionosphere Radio Observatory (GIRO)
;   Lowell GIRO Data Center (LGDC), FastChar.GetBest Web API
;     https://lgdc.uml.edu/fastchar/getbest
;   (旧エンドポイント https://lgdc.uml.edu/common/DIDBGetValues は
;    2026年8月時点で廃止/移動されている模様。応答テキストの形式は
;    ほぼ同じ。)
;   利用規約 (Rules of the Road):
;     https://ulcar.uml.edu/DIDBase/RulesOfTheRoadForDIDBase.htm
;   データは CC-BY-NC-SA 4.0 ライセンス。論文等で使用する場合は
;   データ提供観測点への謝辞が必要です。
;
;   オーストラリアの主な観測点 URSI コード (2026年時点。最新情報は
;   https://ulcar.uml.edu/DIDBase/StationList_new.php で要確認):
;     Darwin      DW41K   (lon = 130.95E)
;     Townsville  TV51R   (lon = 146.85E)
;     Brisbane    BR52P   (lon = 153.06E)
;     Canberra    CB53N   (lon = 149.00E)
;     Camden      CN53L   (lon = 150.67E)
;     Hobart      HO54K   (lon = 147.32E)
;     Perth       PE43K   (lon = 116.13E)
;     Learmonth   LM42B   (lon = 114.10E)
;     Cocos Is.   CS31K   (lon =  96.83E)
;
; REQUIREMENTS:
;   - IDL 8.x (IMAGE/COLORTABLE/COLORBAR などの Function Graphics を使用)
;   - インターネットアクセス。ダウンロードは SPAWN 経由で OS の curl
;     (無ければ wget) コマンドを呼び出す方式にしている。IDLnetURL は
;     計算機環境によって共有ライブラリ(libidn 等)が無く動作しないことが
;     あるため、あえて使用していない。curl/wget もプロキシ等で使えない
;     場合は、ブラウザ等で DIDBGetValues の URL を直接開いて結果を
;     テキスト保存し、
;     giro_es_statistics, /local_files, local_files=['file1.txt','file2.txt']
;     として読み込むこともできる。
;
; USAGE EXAMPLE:
;   IDL> .compile giro_es_statistics
;   IDL> giro_es_statistics, ursi_code='DW41K', station_lon=130.95, $
;          year_start=2015, year_end=2024, threshold=5.0, outdir='.'
;
;   threshold は「スポラディックE発生」とみなす foEs の下限値[MHz]。
;   一般に強い(HF伝搬に影響する)Esの目安として 5 MHz 程度がよく使われるが、
;   研究目的に応じて変更すること。threshold=0 とすると「foEsが少しでも
;   スケーリングされた」割合(Es層検出率)になる。
;-

;----------------------------------------------------------------------
; GIRO/DIDBase の DIDBGetValues API から1つの特性量(例: foEs)を
; 指定期間についてダウンロードし、テキストの行配列として返す
;----------------------------------------------------------------------
;
; 備考: 以前は IDLnetURL を使っていたが、計算機環境によっては
; IDLnetURL(idl_url.so)が依存する共有ライブラリ(libidn.so 等)が
; 見つからず "Error loading sharable executable" で失敗することがある。
; その場合は IDL 本体のライブラリ問題を回避するため、OS に入っている
; curl または wget コマンドを SPAWN 経由で呼び出してダウンロードする方が
; 確実に動く。以下はその方式で実装している。
;
FUNCTION giro_get_data, ursi_code, char_name, t_start, t_end
  compile_opt idl2

  CALDAT, t_start, mo1, dy1, yr1, hh1, mi1, ss1
  CALDAT, t_end,   mo2, dy2, yr2, hh2, mi2, ss2
  ; 2026年8月時点で確認できたエンドポイントは /fastchar/getbest (旧 /common/DIDBGetValues
  ; は廃止/移動された模様)。日付は %2F (=/) と %3A (=:) でURLエンコードして渡す。
  fmt = '(I4.4,"%2F",I2.2,"%2F",I2.2,"+",I2.2,"%3A",I2.2,"%3A",I2.2)'
  from_str = STRING(yr1, mo1, dy1, hh1, mi1, ROUND(ss1), FORMAT=fmt)
  to_str   = STRING(yr2, mo2, dy2, hh2, mi2, ROUND(ss2), FORMAT=fmt)

  query = 'https://lgdc.uml.edu/fastchar/getbest' + $
          '?ursiCode='  + ursi_code + $
          '&charName='  + char_name + $
          '&DMUF=3000'  + $
          '&fromDate='  + from_str  + $
          '&toDate='    + to_str

  PRINT, '  requesting: ', query

  ; --- curl を試す ---
  ; IDL は SPAWN で起動する子プロセスに、IDL 自身の(古い)共有ライブラリを
  ; 含む LD_LIBRARY_PATH を継承させることがあり、その結果システムの
  ; curl/wget が IDL 付属の壊れた libidn 等を参照してしまい
  ; "error while loading shared libraries" で失敗することがある。
  ; そのため、コマンド実行前に LD_LIBRARY_PATH を unset しておく。
  ; また /SH を付けて確実に /bin/sh 経由で実行する(SHELL環境変数が
  ; tcsh 等だと sh 構文が通らないため)。
  lines  = ['']
  status = -1
  err_out = ['']
  cmd = 'unset LD_LIBRARY_PATH; curl -s -S -L --max-time 120 "' + query + '"'
  SPAWN, cmd, lines, err_out, EXIT_STATUS=status, /SH

  ; --- curl が失敗した場合は wget を試す ---
  IF (status NE 0) || (N_ELEMENTS(lines) EQ 0) || (STRLEN(STRTRIM(lines[0],2)) EQ 0) THEN BEGIN
    PRINT, '  curl failed (exit status ', status, '). stderr:'
    IF N_ELEMENTS(err_out) GT 0 THEN PRINT, '    ' + err_out

    tmpfile = FILEPATH(ursi_code + '_' + char_name + '_tmp.txt', /TMP)
    cmd2 = 'unset LD_LIBRARY_PATH; wget -nv -O "' + tmpfile + '" "' + query + '" 2>&1'
    err_out2 = ['']
    SPAWN, cmd2, wget_msg, err_out2, EXIT_STATUS=status2, /SH
    IF (status2 EQ 0) && FILE_TEST(tmpfile) THEN BEGIN
      lines = giro_read_local_file(tmpfile)
      FILE_DELETE, tmpfile, /ALLOW_NONEXISTENT
      status = 0
    ENDIF ELSE BEGIN
      PRINT, '  wget failed (exit status ', status2, '). output:'
      IF N_ELEMENTS(wget_msg) GT 0 THEN PRINT, '    ' + wget_msg
    ENDELSE
  ENDIF

  IF (status NE 0) || (N_ELEMENTS(lines) EQ 0) || (STRLEN(STRTRIM(lines[0],2)) EQ 0) THEN BEGIN
    PRINT, '  download failed. 上のエラーメッセージを確認してください' + $
           ' (コマンド自体が無い場合は command not found、外部接続が' + $
           ' ブロックされている場合は timeout/Could not resolve host 等が出ます)。'
    RETURN, ''
  ENDIF

  RETURN, lines
END

;----------------------------------------------------------------------
; ローカルに保存済みの DIDBGetValues 出力テキストファイルを読み込む
; (ネットワークアクセスできない環境向けの代替手段)
;----------------------------------------------------------------------
FUNCTION giro_read_local_file, filename
  compile_opt idl2
  nlines = FILE_LINES(filename)
  IF nlines LE 0 THEN RETURN, ''
  lines = STRARR(nlines)
  OPENR, lun, filename, /GET_LUN
  READF, lun, lines
  FREE_LUN, lun
  RETURN, lines
END

;----------------------------------------------------------------------
; DIDBGetValues のテキスト出力から、指定した特性量(param_name, 例: 'foEs')
; の時刻・数値の系列を取り出す。
;   フォーマット例:
;     # ... ヘッダ行 ...
;     #Time CS foEs QD
;     2020-01-01T00:15:00.000Z 70 5.30 //
;   ヘッダ行 "#Time ..." を毎回解析してカラム位置を自動判定するため、
;   charName に複数の特性量を並べて要求した場合にも対応できる。
;----------------------------------------------------------------------
FUNCTION giro_parse_data, lines, param_name
  compile_opt idl2

  nlines  = N_ELEMENTS(lines)
  col_idx = -1

  jd  = DBLARR(nlines)
  val = FLTARR(nlines)
  n   = 0L

  FOR i = 0L, nlines-1 DO BEGIN
    line = STRTRIM(lines[i], 2)
    IF STRLEN(line) EQ 0 THEN CONTINUE

    IF STRMID(line,0,1) EQ '#' THEN BEGIN
      ; カラム名を示すヘッダ行 "#Time CS foEs QD ..." を探す
      body = STRTRIM(STRMID(line,1), 2)
      toks = STRSPLIT(body, /EXTRACT)
      IF (N_ELEMENTS(toks) GE 2) && (STRLOWCASE(toks[0]) EQ 'time') THEN BEGIN
        w = WHERE(toks EQ param_name, cnt)
        IF cnt GT 0 THEN col_idx = w[0]
      ENDIF
      CONTINUE
    ENDIF

    IF col_idx LT 0 THEN CONTINUE   ; まだヘッダが見つかっていない/該当パラメータなし

    fields = STRSPLIT(line, /EXTRACT)
    IF N_ELEMENTS(fields) LE col_idx THEN CONTINUE

    t = fields[0]                                ; 例: 2020-01-01T00:15:00.000Z
    IF STRLEN(t) LT 19 THEN CONTINUE
    yr = FIX(STRMID(t,0,4))  &  mo = FIX(STRMID(t,5,2))  &  dy = FIX(STRMID(t,8,2))
    hh = FIX(STRMID(t,11,2)) &  mi = FIX(STRMID(t,14,2)) &  ss = FIX(STRMID(t,17,2))
    jd[n] = JULDAY(mo, dy, yr, hh, mi, ss)

    vstr = fields[col_idx]
    IF STREGEX(vstr, '^-?[0-9]+\.?[0-9]*$', /BOOLEAN) THEN $
      val[n] = FLOAT(vstr) $
    ELSE $
      val[n] = !VALUES.F_NAN            ; '//' 等はデータなし(Esなし)を意味する

    n = n + 1L
  ENDFOR

  IF n EQ 0 THEN RETURN, {n:0L}
  RETURN, {n:n, jd:jd[0:n-1], val:val[0:n-1]}
END

;----------------------------------------------------------------------
; 月(1-12)×地方時(0-23時)ごとのスポラディックE発生頻度(%)を計算する。
;   発生頻度 = (foEs >= threshold となった観測回数) / (全観測回数) × 100
;   地方時は station_lon から近似的に太陽地方時として計算 (LT = UT + lon/15)
;----------------------------------------------------------------------
FUNCTION es_occurrence_matrix, jd, foEs, lon_deg, threshold=threshold
  compile_opt idl2
  IF N_ELEMENTS(threshold) EQ 0 THEN threshold = 5.0   ; MHz

  n_count  = LONARR(24,12)   ; [hour, month] 全観測回数
  es_count = LONARR(24,12)   ; [hour, month] 閾値以上のEs観測回数

  n = N_ELEMENTS(jd)
  FOR i = 0L, n-1 DO BEGIN
    CALDAT, jd[i], mo, dy, yr, hh, mi, ss
    lt_hour = (hh + mi/60.0D + lon_deg/15.0D) MOD 24.0D
    IF lt_hour LT 0 THEN lt_hour = lt_hour + 24.0D
    ih = FIX(lt_hour) < 23

    n_count[ih, mo-1] = n_count[ih, mo-1] + 1
    IF FINITE(foEs[i]) THEN BEGIN
      IF foEs[i] GE threshold THEN es_count[ih, mo-1] = es_count[ih, mo-1] + 1
    ENDIF
  ENDFOR

  occ = FLTARR(24,12)
  FOR m = 0, 11 DO BEGIN
    FOR h = 0, 23 DO BEGIN
      IF n_count[h,m] GT 0 THEN $
        occ[h,m] = 100.0*es_count[h,m]/n_count[h,m] $
      ELSE $
        occ[h,m] = !VALUES.F_NAN
    ENDFOR
  ENDFOR

  RETURN, {occurrence:occ, n_total:n_count, n_es:es_count}
END

;----------------------------------------------------------------------
; メインプログラム
;----------------------------------------------------------------------
PRO giro_es_statistics, ursi_code=ursi_code, station_lon=station_lon, $
                         year_start=year_start, year_end=year_end, $
                         threshold=threshold, outdir=outdir, $
                         local_files=local_files
  compile_opt idl2

  IF N_ELEMENTS(ursi_code)   EQ 0 THEN ursi_code   = 'DW41K'   ; Darwin
  IF N_ELEMENTS(station_lon) EQ 0 THEN station_lon = 130.95D
  IF N_ELEMENTS(year_start)  EQ 0 THEN year_start  = 2015
  IF N_ELEMENTS(year_end)    EQ 0 THEN year_end    = 2024
  IF N_ELEMENTS(threshold)   EQ 0 THEN threshold   = 5.0
  IF N_ELEMENTS(outdir)      EQ 0 THEN outdir      = '.'

  all_jd  = !NULL
  all_val = !NULL

  IF N_ELEMENTS(local_files) GT 0 THEN BEGIN
    ;-------------------------------------------------------------
    ; あらかじめブラウザ等で保存しておいたテキストファイルを読み込む場合
    ;-------------------------------------------------------------
    FOR k = 0, N_ELEMENTS(local_files)-1 DO BEGIN
      lines = giro_read_local_file(local_files[k])
      d = giro_parse_data(lines, 'foEs')
      IF d.n GT 0 THEN BEGIN
        IF N_ELEMENTS(all_jd) EQ 0 THEN all_jd  = d.jd  ELSE all_jd  = [all_jd,  d.jd]
        IF N_ELEMENTS(all_val) EQ 0 THEN all_val = d.val ELSE all_val = [all_val, d.val]
      ENDIF
    ENDFOR
  ENDIF ELSE BEGIN
    ;-------------------------------------------------------------
    ; GIRO/DIDBase から年ごとに分割してダウンロード
    ; (一度に長期間を要求すると失敗しやすいため1年単位で取得)
    ;-------------------------------------------------------------
    FOR yr = year_start, year_end DO BEGIN
      t0 = JULDAY(1, 1,  yr, 0, 0, 0)
      t1 = JULDAY(12, 31, yr, 23, 59, 0)
      lines = giro_get_data(ursi_code, 'foEs', t0, t1)
      IF SIZE(lines, /TYPE) NE 7 THEN CONTINUE   ; ダウンロード失敗
      d = giro_parse_data(lines, 'foEs')
      IF d.n EQ 0 THEN BEGIN
        PRINT, '  -> parse結果0件。サーバー応答の先頭数行:'
        nshow = 5 < N_ELEMENTS(lines)
        FOR ii = 0, nshow-1 DO PRINT, '    [' + STRTRIM(ii,2) + '] ' + lines[ii]
        CONTINUE
      ENDIF
      IF N_ELEMENTS(all_jd) EQ 0 THEN all_jd  = d.jd  ELSE all_jd  = [all_jd,  d.jd]
      IF N_ELEMENTS(all_val) EQ 0 THEN all_val = d.val ELSE all_val = [all_val, d.val]
      PRINT, yr, d.n, FORMAT='("  ",I4," : ",I6," records")'
    ENDFOR
  ENDELSE

  IF N_ELEMENTS(all_jd) EQ 0 THEN BEGIN
    PRINT, 'データを取得できませんでした。ネットワーク接続・観測点コード・期間を確認してください。'
    RETURN
  ENDIF

  ; 生データを保存しておく(再ダウンロード不要にするため)
  SAVE, all_jd, all_val, FILENAME = outdir + PATH_SEP() + ursi_code + '_foEs_raw.sav'

  ; 統計計算
  stats = es_occurrence_matrix(all_jd, all_val, station_lon, threshold=threshold)

  ; ---- 図示: 月 × 地方時 の発生頻度マップ ----
  months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  hours  = INDGEN(24)

  ct = COLORTABLE(33)   ; blue-red rainbow
  im = IMAGE(stats.occurrence, hours, INDGEN(12)+1, $
             RGB_TABLE = ct, /ASPECT_RATIO, $
             XTITLE = 'Local Time (hour)', YTITLE = 'Month', $
             TITLE = 'Sporadic-E Occurrence Rate (foEs $\geq$ ' + $
                     STRTRIM(threshold,2) + ' MHz)  :  ' + ursi_code, $
             YTICKVALUES = INDGEN(12)+1, YTICKNAME = months, $
             MIN_VALUE = 0, MAX_VALUE = 100, DIMENSIONS = [700,500])
  cb = COLORBAR(TARGET = im, TITLE = 'Occurrence rate (%)', ORIENTATION = 1, $
                POSITION = [0.90, 0.15, 0.93, 0.85])
  im.Save, outdir + PATH_SEP() + ursi_code + '_Es_occurrence.png', RESOLUTION = 200

  PRINT, '----------------------------------------------------'
  PRINT, 'Total ionograms used : ', N_ELEMENTS(all_jd)
  PRINT, 'Figure saved to      : ', outdir + PATH_SEP() + ursi_code + '_Es_occurrence.png'
  PRINT, 'Raw data saved to    : ', outdir + PATH_SEP() + ursi_code + '_foEs_raw.sav'
END
