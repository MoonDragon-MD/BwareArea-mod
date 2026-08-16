#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch-FIX-2026.py - BwareArea 0.6.7 by MoonDragon
https://github.com/MoonDragon-MD/BwareArea-mod/

Risolve:
1) Wizard permessi ad ogni avvio
2) Conteggio POI non aggiornato dopo import
3) Crash se GPS spento
4) GPS che si "sgancia" (startForeground troppo tardi + notifica invalida)
5) Overlay/doppio-tap che riapre il benvenuto e ferma il service
+ crash ClassCastException toolbar + crash icona notifica
"""

from __future__ import print_function
import os
import shutil
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "app", "src", "main", "java", "fr", "byped", "bwarearea")
RES_LAYOUT = os.path.join(BASE, "app", "src", "main", "res", "layout")
MANIFEST = os.path.join(BASE, "app", "src", "main", "AndroidManifest.xml")

MAIN = os.path.join(SRC, "MainActivity.java")
SERVICE = os.path.join(SRC, "FloatingWarnerService.java")
PERM = os.path.join(SRC, "WhyPermissionActivity.java")

BACKUP_SUFFIX = ".backup_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def backup(path):
    if os.path.isfile(path):
        dst = path + BACKUP_SUFFIX
        shutil.copy2(path, dst)
        print("  backup ->", os.path.basename(dst))


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("  OK  ", os.path.relpath(path, BASE))


# =============================================================================
# MAINACTIVITY
# =============================================================================

def patch_main(content):
    # --- import extra ---
    if "import android.location.LocationManager;" not in content:
        content = content.replace(
            "import android.net.Uri;",
            "import android.net.Uri;\nimport android.location.LocationManager;"
        )
    if "import android.support.v7.app.AlertDialog;" not in content:
        content = content.replace(
            "import android.support.v7.app.AppCompatActivity;",
            "import android.support.v7.app.AppCompatActivity;\nimport android.support.v7.app.AlertDialog;"
        )
    if "import android.content.DialogInterface;" not in content:
        content = content.replace(
            "import android.content.Intent;",
            "import android.content.Intent;\nimport android.content.DialogInterface;"
        )

    # --- onCreate: ordine corretto + toolbar giusto + skip wizard se service attivo ---
    old_oncreate_head = '''    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        pref = getSharedPreferences("settings", Context.MODE_PRIVATE);
        initCrashReporter();
        Toolbar toolbar = (Toolbar) findViewById(R.id.appbar);
        setSupportActionBar(toolbar);
        setContentView(R.layout.activity_main);



        // Check if we have all required permissions (if not, start the WhyPermissionActivity)
        boolean canUseGPS = Build.VERSION.SDK_INT < 23 || checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
        boolean canAccessExternalStorage = Build.VERSION.SDK_INT < 23 || (checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED);
        boolean canOverlay = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(MainActivity.this);
        boolean canSkipDoze = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || ((PowerManager)getSystemService(Context.POWER_SERVICE)).isIgnoringBatteryOptimizations(getPackageName());
        if (!canUseGPS || !canAccessExternalStorage || !canOverlay || !canSkipDoze)
        {
            // Need to start the WhyPermissionActivity
            Intent intent = new Intent(this, WhyPermissionActivity.class);
            startActivity(intent);
        }'''

    new_oncreate_head = '''    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        pref = getSharedPreferences("settings", Context.MODE_PRIVATE);
        initCrashReporter();

        setContentView(R.layout.activity_main);

        // R.id.appbar e' AppBarLayout, il Toolbar vero e' R.id.toolbar
        Toolbar toolbar = (Toolbar) findViewById(R.id.toolbar);
        if (toolbar != null) {
            setSupportActionBar(toolbar);
        }

        // Se il service e' gia' attivo non rifare il wizard permessi
        if (!FloatingWarnerService.isRunning() && !hasAllPermissions()) {
            startActivity(new Intent(this, WhyPermissionActivity.class));
        }'''

    if old_oncreate_head in content:
        content = content.replace(old_oncreate_head, new_oncreate_head)
    else:
        print("  WARN: blocco onCreate non trovato esattamente (forse gia' patchato)")

    # --- hasAllPermissions ---
    if "private boolean hasAllPermissions()" not in content:
        method = '''
    private boolean hasAllPermissions() {
        boolean canUseGPS = Build.VERSION.SDK_INT < 23
                || checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
        boolean canAccessExternalStorage = Build.VERSION.SDK_INT < 23
                || (checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED
                    && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED);
        boolean canOverlay = Build.VERSION.SDK_INT < Build.VERSION_CODES.M
                || Settings.canDrawOverlays(this);
        boolean canSkipDoze = Build.VERSION.SDK_INT < Build.VERSION_CODES.M
                || ((PowerManager) getSystemService(Context.POWER_SERVICE)).isIgnoringBatteryOptimizations(getPackageName());
        return canUseGPS && canAccessExternalStorage && canOverlay && canSkipDoze;
    }

'''
        content = content.replace(
            "    private void errorToast() {",
            method + "    private void errorToast() {"
        )

    # --- startService con check GPS (senza lambda) ---
    old_start = '''    /** Start the main service and finish this activity */
    private void startService()
    {
        ContextCompat.startForegroundService(this, new Intent(MainActivity.this, FloatingWarnerService.class));
        Toast.makeText(getApplicationContext(), R.string.started_service, Toast.LENGTH_LONG).show();
//        MainActivity.this.finish();
    }'''

    new_start = '''    /** Start the main service and finish this activity */
    private void startService()
    {
        LocationManager lm = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        boolean gpsEnabled = lm != null && lm.isProviderEnabled(LocationManager.GPS_PROVIDER);
        if (!gpsEnabled) {
            new AlertDialog.Builder(this)
                    .setTitle("GPS disattivato")
                    .setMessage("Il GPS deve essere attivo per usare BwareArea.\\nVuoi attivarlo ora?")
                    .setPositiveButton("Attiva", new DialogInterface.OnClickListener() {
                        @Override
                        public void onClick(DialogInterface dialog, int which) {
                            startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS));
                        }
                    })
                    .setNegativeButton("Annulla", null)
                    .show();
            return;
        }
        ContextCompat.startForegroundService(this, new Intent(MainActivity.this, FloatingWarnerService.class));
        Toast.makeText(getApplicationContext(), R.string.started_service, Toast.LENGTH_LONG).show();
    }'''

    content = content.replace(old_start, new_start)

    # --- click Start/Stop intelligente ---
    old_click = '''        startService = (Button) findViewById(R.id.startStop);
        startService.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startService();
            }
        });'''

    new_click = '''        startService = (Button) findViewById(R.id.startStop);
        startService.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (FloatingWarnerService.isRunning()) {
                    stopService(new Intent(MainActivity.this, FloatingWarnerService.class));
                    startService.setText(R.string.start_service);
                } else {
                    startService();
                    startService.setText(R.string.stop_service);
                }
            }
        });'''

    content = content.replace(old_click, new_click)

    # --- onResume ---
    if "protected void onResume()" not in content:
        on_resume = '''
    @Override
    protected void onResume() {
        super.onResume();
        if (startService == null || POIDBLabel == null) return;
        if (FloatingWarnerService.isRunning()) {
            startService.setText(R.string.stop_service);
            long count = pref.getLong("poiCount", 0);
            POIDBLabel.setText(String.format(getString(R.string.point_of_interest_database_with_poi), (int) count));
        } else {
            startService.setText(R.string.start_service);
        }
    }

'''
        content = content.replace(
            '''    @Override
    @TargetApi(23)
    protected void onPause()''',
            on_resume + '''    @Override
    @TargetApi(23)
    protected void onPause()'''
        )

    # --- import: aggiorna conteggio POI ---
    old_post = '''        @Override
        protected void onPostExecute(String result) {
            progressBar.setVisibility(View.GONE);
            POIDBLabel.setText(result);

        }'''

    new_post = '''        @Override
        protected void onPostExecute(String result) {
            progressBar.setVisibility(View.GONE);
            long count = pref.getLong("poiCount", 0);
            POIDBLabel.setText(String.format(getString(R.string.point_of_interest_database_with_poi), (int) count));
        }'''

    content = content.replace(old_post, new_post)

    return content


# =============================================================================
# FLOATINGWARNERSERVICE
# =============================================================================

def patch_service(content):
    # import
    if "import android.app.NotificationChannel;" not in content:
        content = content.replace(
            "import android.app.Notification;",
            "import android.app.Notification;\nimport android.app.NotificationChannel;\nimport android.app.NotificationManager;"
        )

    # campo statico isRunning
    if "private static boolean serviceRunning" not in content:
        content = content.replace(
            '''    private int poiCount;
    private FileWriter logToFile;
    private boolean trackOpened;



    @Nullable''',
            '''    private int poiCount;
    private FileWriter logToFile;
    private boolean trackOpened;

    private static boolean serviceRunning = false;

    public static boolean isRunning() {
        return serviceRunning;
    }

    @Nullable'''
        )

    # serviceRunning = true all'inizio di onCreate + startForeground SUBITO
    old_oncreate = '''    public void onCreate() {
        super.onCreate();
        binder = new Binder();

        // Check if we have some action to perform first
        collection = new POICollection(this);'''

    new_oncreate = '''    public void onCreate() {
        super.onCreate();
        serviceRunning = true;
        binder = new Binder();

        // Obbligatorio: startForeground entro pochi secondi da startForegroundService
        // altrimenti Android uccide il service (e il GPS sembra "sganciarsi")
        showLocationNotification();

        // Check if we have some action to perform first
        collection = new POICollection(this);'''

    content = content.replace(old_oncreate, new_oncreate)

    # onDestroy
    content = content.replace(
        '''    public void onDestroy() {
        stopLocation();
        super.onDestroy();''',
        '''    public void onDestroy() {
        serviceRunning = false;
        stopLocation();
        super.onDestroy();'''
    )

    # notifica corretta (icona + channel + flags)
    old_notif = '''    private void showLocationNotification()
    {
        Intent intent = new Intent("finish_service");
        intent.setClass(this, FloatingWarnerService.class);
        // You can also include some extra data.
        intent.putExtra("message", "From service!");
        Notification notification = new NotificationCompat.Builder(this, "main")
                .setContentTitle(getString(R.string.bware_is_running))
                .setContentText(getString(R.string.tap_to_settings))
                .setSmallIcon(R.mipmap.ic_launcher_bware)
                .setContentIntent(PendingIntent.getService(this, 0, intent, 0))
                .setOngoing(true)
                .build();



        startForeground(1, notification);

    }'''

    new_notif = '''    private void showLocationNotification()
    {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    "main",
                    "BwareArea Service",
                    NotificationManager.IMPORTANCE_LOW);
            channel.setShowBadge(false);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.createNotificationChannel(channel);
            }
        }

        Intent intent = new Intent("finish_service");
        intent.setClass(this, FloatingWarnerService.class);
        intent.putExtra("message", "From service!");

        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }

        // NON usare mipmap/launcher come small icon -> crash su molti device
        Notification notification = new NotificationCompat.Builder(this, "main")
                .setContentTitle(getString(R.string.bware_is_running))
                .setContentText(getString(R.string.tap_to_settings))
                .setSmallIcon(android.R.drawable.ic_menu_mylocation)
                .setContentIntent(PendingIntent.getService(this, 0, intent, flags))
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build();

        startForeground(1, notification);
    }'''

    content = content.replace(old_notif, new_notif)

    # doppio-tap: apri MainActivity SENZA fermare il service
    old_double = '''                public boolean onDoubleTap(final MotionEvent e) {
                    // Should trigger our main activity and stop the service
                    Intent intent = new Intent(FloatingWarnerService.this, MainActivity.class);
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    startActivity(intent);

                    //close the service and remove the fab view
                    stopCleanly();
                    return true;
                }'''

    new_double = '''                public boolean onDoubleTap(final MotionEvent e) {
                    // Apri MainActivity senza fermare il service / overlay
                    Intent intent = new Intent(FloatingWarnerService.this, MainActivity.class);
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                            | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
                            | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                    startActivity(intent);
                    return true;
                }'''

    content = content.replace(old_double, new_double)

    # doneImporting: non richiamare showLocationNotification se gia' fatto
    # (resta ok anche se lo richiama: e' idempotente)
    return content


# =============================================================================
# WHYPERMISSIONACTIVITY
# =============================================================================

def patch_perm(content):
    if "import android.content.SharedPreferences;" not in content:
        content = content.replace(
            "import android.content.Intent;",
            "import android.content.Intent;\nimport android.content.SharedPreferences;"
        )

    old = "                        if (position == 5) finish();"
    new = '''                        if (position == 5) {
                            SharedPreferences prefs = getSharedPreferences("permissions_state", MODE_PRIVATE);
                            prefs.edit().putBoolean("wizard_done", true).apply();
                            finish();
                        }'''
    content = content.replace(old, new)
    return content


# =============================================================================
# MANIFEST (FOREGROUND_SERVICE)
# =============================================================================

def patch_manifest(content):
    if "android.permission.FOREGROUND_SERVICE" not in content:
        content = content.replace(
            '    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />',
            '    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />\n'
            '    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />'
        )
    return content


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("BWAREAREA Patch-FIX-2026")
    print("=" * 70)

    for p, name in [(MAIN, "MainActivity.java"), (SERVICE, "FloatingWarnerService.java"),
                    (PERM, "WhyPermissionActivity.java"), (MANIFEST, "AndroidManifest.xml")]:
        if not os.path.isfile(p):
            print("ERRORE: manca", name)
            return
        print("trovato:", name)

    print("\n[1/4] MainActivity.java")
    backup(MAIN)
    write(MAIN, patch_main(read(MAIN)))

    print("\n[2/4] FloatingWarnerService.java")
    backup(SERVICE)
    write(SERVICE, patch_service(read(SERVICE)))

    print("\n[3/4] WhyPermissionActivity.java")
    backup(PERM)
    write(PERM, patch_perm(read(PERM)))

    print("\n[4/4] AndroidManifest.xml")
    backup(MANIFEST)
    write(MANIFEST, patch_manifest(read(MANIFEST)))

    print("\n" + "=" * 70)
    print("PATCH COMPLETATA")
    print("=" * 70)
    print("""
Prossimi passi:
  1. ./setup_and_build.sh
  2. adb uninstall fr.byped.bwarearea
  3. Installa il nuovo APK
  4. Concedi i permessi UNA volta e testa i 5 punti

Note:
  - Icona notifica = icona di sistema (niente piu' crash)
  - startForeground chiamato subito in onCreate (GPS resta agganciato)
  - Doppio-tap sull'overlay apre l'app senza chiudere il service
  - Wizard permessi non riparte se il service e' gia' attivo
""")


if __name__ == "__main__":
    main()