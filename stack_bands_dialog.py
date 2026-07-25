import os
from datetime import datetime

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QListWidget, QAbstractItemView,
    QMessageBox, QProgressBar, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsRasterLayer, QgsProject
from osgeo import gdal

gdal.UseExceptions()


class StackBandsDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Stack Bands S2")
        self.resize(600, 480)

        layout_principal = QVBoxLayout()
        onglets = QTabWidget()
        onglets.addTab(self._build_onglet_stack(), "Empiler les bandes")
        onglets.addTab(self._build_onglet_renommer(), "Renommer les bandes")
        layout_principal.addWidget(onglets)
        self.setLayout(layout_principal)

    # ------------------------------------------------------------------
    # ONGLET 1 - EMPILEMENT DES BANDES
    # ------------------------------------------------------------------
    def _build_onglet_stack(self):
        widget = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Dossier contenant les bandes (ex. R10m) :"))
        dossier_layout = QHBoxLayout()
        self.champ_dossier = QLineEdit()
        bouton_parcourir = QPushButton("Parcourir...")
        bouton_parcourir.clicked.connect(self.choisir_dossier)
        dossier_layout.addWidget(self.champ_dossier)
        dossier_layout.addWidget(bouton_parcourir)
        layout.addLayout(dossier_layout)

        layout.addWidget(QLabel(
            "Bandes détectées (.jp2 / .tif) - sélectionnez et ordonnez "
            "dans l'ordre d'empilement souhaité :"
        ))
        self.liste_fichiers = QListWidget()
        self.liste_fichiers.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.liste_fichiers.setDragDropMode(QAbstractItemView.InternalMove)
        layout.addWidget(self.liste_fichiers)

        ordre_layout = QHBoxLayout()
        bouton_monter = QPushButton("Monter ↑")
        bouton_monter.clicked.connect(self.monter_selection)
        bouton_descendre = QPushButton("Descendre ↓")
        bouton_descendre.clicked.connect(self.descendre_selection)
        bouton_retirer = QPushButton("Retirer ✕")
        bouton_retirer.setToolTip(
            "Retire le(s) fichier(s) sélectionné(s) de la liste "
            "(ne supprime rien du disque)"
        )
        bouton_retirer.clicked.connect(self.retirer_selection)
        ordre_layout.addWidget(bouton_monter)
        ordre_layout.addWidget(bouton_descendre)
        ordre_layout.addWidget(bouton_retirer)
        layout.addLayout(ordre_layout)

        layout.addWidget(QLabel("Nom du fichier de sortie (.tif) :"))
        self.champ_sortie = QLineEdit("stack_bandes.tif")
        layout.addWidget(self.champ_sortie)

        self.barre_progression = QProgressBar()
        self.barre_progression.setValue(0)
        layout.addWidget(self.barre_progression)

        boutons_layout = QHBoxLayout()
        bouton_executer = QPushButton("Exécuter le stack")
        bouton_executer.clicked.connect(self.executer_stack)
        bouton_fermer = QPushButton("Fermer")
        bouton_fermer.clicked.connect(self.close)
        boutons_layout.addWidget(bouton_executer)
        boutons_layout.addWidget(bouton_fermer)
        layout.addLayout(boutons_layout)

        widget.setLayout(layout)
        return widget

    def choisir_dossier(self):
        dossier = QFileDialog.getExistingDirectory(self, "Choisir le dossier des bandes")
        if dossier:
            self.champ_dossier.setText(dossier)
            self.detecter_bandes(dossier)

    def detecter_bandes(self, dossier):
        self.liste_fichiers.clear()
        extensions = (".jp2", ".tif", ".tiff")
        fichiers = sorted([
            f for f in os.listdir(dossier)
            if f.lower().endswith(extensions)
        ])
        for f in fichiers:
            self.liste_fichiers.addItem(f)

    def monter_selection(self):
        ligne = self.liste_fichiers.currentRow()
        if ligne > 0:
            item = self.liste_fichiers.takeItem(ligne)
            self.liste_fichiers.insertItem(ligne - 1, item)
            self.liste_fichiers.setCurrentRow(ligne - 1)

    def descendre_selection(self):
        ligne = self.liste_fichiers.currentRow()
        if ligne < self.liste_fichiers.count() - 1 and ligne != -1:
            item = self.liste_fichiers.takeItem(ligne)
            self.liste_fichiers.insertItem(ligne + 1, item)
            self.liste_fichiers.setCurrentRow(ligne + 1)

    def retirer_selection(self):
        """Retire de la liste le(s) fichier(s) non désiré(s) pour le stack.
        N'affecte que la sélection dans la fenêtre, aucun fichier n'est
        supprimé du dossier."""
        lignes_selectionnees = sorted(
            [self.liste_fichiers.row(item) for item in self.liste_fichiers.selectedItems()],
            reverse=True,
        )
        if not lignes_selectionnees:
            QMessageBox.information(
                self, "Information",
                "Sélectionnez d'abord un ou plusieurs fichiers dans la liste à retirer."
            )
            return
        for ligne in lignes_selectionnees:
            self.liste_fichiers.takeItem(ligne)

    @staticmethod
    def extraire_nom_bande(nom_fichier):
        """Extrait un nom de bande court à partir du nom de fichier,
        ex: T31PDK_20260127T101301_B02_10m.jp2 -> B02"""
        base = os.path.splitext(nom_fichier)[0]
        parties = base.split("_")
        for p in parties:
            if len(p) in (2, 3) and p[0] in ("B", "b") and p[1:].isdigit():
                return p.upper()
            if p.upper() in ("B8A",):
                return p.upper()
        return base  # repli : nom complet si aucun motif reconnu

    def ecrire_journal(self, dossier, objectif, actions, resultat):
        chemin_journal = os.path.join(dossier, "journal_technique.txt")
        horodatage = datetime.now().strftime("%d/%m/%Y %H:%M")
        entree = (
            f"\n{'='*70}\n"
            f"Date : {horodatage}\n"
            f"Objectif : {objectif}\n"
            f"Actions exécutées :\n{actions}\n"
            f"Résultat : {resultat}\n"
        )
        with open(chemin_journal, "a", encoding="utf-8") as f:
            f.write(entree)

    def executer_stack(self):
        dossier = self.champ_dossier.text().strip()
        nom_sortie = self.champ_sortie.text().strip()

        if not dossier or not os.path.isdir(dossier):
            QMessageBox.warning(self, "Erreur", "Veuillez choisir un dossier valide.")
            return

        if self.liste_fichiers.count() == 0:
            QMessageBox.warning(self, "Erreur", "Aucune bande détectée ou sélectionnée.")
            return

        if not nom_sortie.lower().endswith(".tif"):
            nom_sortie += ".tif"

        chemins = [
            os.path.join(dossier, self.liste_fichiers.item(i).text())
            for i in range(self.liste_fichiers.count())
        ]
        noms_bandes = [self.extraire_nom_bande(os.path.basename(c)) for c in chemins]

        fichier_sortie = os.path.join(dossier, nom_sortie)
        fichier_vrt = os.path.join(dossier, "_temp_stack.vrt")

        try:
            self.barre_progression.setValue(10)

            vrt_options = gdal.BuildVRTOptions(separate=True)
            vrt_ds = gdal.BuildVRT(fichier_vrt, chemins, options=vrt_options)
            vrt_ds = None
            self.barre_progression.setValue(40)

            translate_options = gdal.TranslateOptions(
                format="GTiff",
                creationOptions=["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES"],
            )
            out_ds = gdal.Translate(fichier_sortie, fichier_vrt, options=translate_options)
            self.barre_progression.setValue(75)

            for i, nom in enumerate(noms_bandes, start=1):
                out_ds.GetRasterBand(i).SetDescription(nom)

            out_ds.FlushCache()
            out_ds = None

            if os.path.exists(fichier_vrt):
                os.remove(fichier_vrt)

            self.barre_progression.setValue(90)

            couche = QgsRasterLayer(fichier_sortie, os.path.splitext(nom_sortie)[0])
            if couche.isValid():
                QgsProject.instance().addMapLayer(couche)
            else:
                QMessageBox.warning(
                    self, "Attention",
                    "Le fichier a été créé mais n'a pas pu être chargé automatiquement."
                )

            self.barre_progression.setValue(100)

            actions = "\n".join(
                [f"  - Bande {i+1} ({nom}) depuis {os.path.basename(c)}"
                 for i, (nom, c) in enumerate(zip(noms_bandes, chemins))]
            )
            self.ecrire_journal(
                dossier=dossier,
                objectif=f"Empilement de {len(chemins)} bandes via le plugin Stack Bands S2",
                actions=actions,
                resultat=f"Fichier créé et chargé dans QGIS : {fichier_sortie} "
                         f"(bandes : {', '.join(noms_bandes)})",
            )

            QMessageBox.information(
                self, "Succès",
                f"Stack créé et chargé dans QGIS :\n{fichier_sortie}"
            )

        except Exception as e:
            self.barre_progression.setValue(0)
            QMessageBox.critical(self, "Erreur", f"Échec du traitement :\n{str(e)}")

    # ------------------------------------------------------------------
    # ONGLET 2 - RENOMMAGE DES BANDES D'UNE IMAGE EXISTANTE
    # ------------------------------------------------------------------
    def _build_onglet_renommer(self):
        widget = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Image raster à traiter (.tif) :"))
        fichier_layout = QHBoxLayout()
        self.champ_image_renommer = QLineEdit()
        bouton_parcourir_image = QPushButton("Parcourir...")
        bouton_parcourir_image.clicked.connect(self.choisir_image_renommer)
        fichier_layout.addWidget(self.champ_image_renommer)
        fichier_layout.addWidget(bouton_parcourir_image)
        layout.addLayout(fichier_layout)

        layout.addWidget(QLabel(
            "Double-cliquez sur la colonne \"Nouveau nom\" pour modifier le nom de chaque bande :"
        ))
        self.table_bandes = QTableWidget(0, 3)
        self.table_bandes.setHorizontalHeaderLabels(["Bande", "Nom actuel", "Nouveau nom"])
        self.table_bandes.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_bandes.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_bandes.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.table_bandes)

        boutons_layout = QHBoxLayout()
        bouton_enregistrer = QPushButton("Enregistrer les noms")
        bouton_enregistrer.clicked.connect(self.enregistrer_noms_bandes)
        bouton_fermer2 = QPushButton("Fermer")
        bouton_fermer2.clicked.connect(self.close)
        boutons_layout.addWidget(bouton_enregistrer)
        boutons_layout.addWidget(bouton_fermer2)
        layout.addLayout(boutons_layout)

        widget.setLayout(layout)
        return widget

    def choisir_image_renommer(self):
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image raster", "", "GeoTIFF (*.tif *.tiff);;Tous les fichiers (*)"
        )
        if chemin:
            self.champ_image_renommer.setText(chemin)
            self.charger_bandes_pour_renommage(chemin)

    def charger_bandes_pour_renommage(self, chemin):
        self.table_bandes.setRowCount(0)
        try:
            ds = gdal.Open(chemin)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir le fichier :\n{str(e)}")
            return

        if ds is None:
            QMessageBox.critical(self, "Erreur", "Fichier raster invalide.")
            return

        nb_bandes = ds.RasterCount
        self.table_bandes.setRowCount(nb_bandes)
        for i in range(1, nb_bandes + 1):
            band = ds.GetRasterBand(i)
            nom_actuel = band.GetDescription() or "(sans nom)"

            item_bande = QTableWidgetItem(f"Bande {i}")
            item_bande.setFlags(item_bande.flags() & ~Qt.ItemIsEditable)
            self.table_bandes.setItem(i - 1, 0, item_bande)

            item_actuel = QTableWidgetItem(nom_actuel)
            item_actuel.setFlags(item_actuel.flags() & ~Qt.ItemIsEditable)
            self.table_bandes.setItem(i - 1, 1, item_actuel)

            item_nouveau = QTableWidgetItem(
                nom_actuel if nom_actuel != "(sans nom)" else f"B{i}"
            )
            self.table_bandes.setItem(i - 1, 2, item_nouveau)

        ds = None

    def enregistrer_noms_bandes(self):
        chemin = self.champ_image_renommer.text().strip()
        if not chemin or not os.path.isfile(chemin):
            QMessageBox.warning(self, "Erreur", "Veuillez choisir une image raster valide.")
            return

        if self.table_bandes.rowCount() == 0:
            QMessageBox.warning(self, "Erreur", "Aucune bande chargée.")
            return

        try:
            ds = gdal.Open(chemin, gdal.GA_Update)
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur",
                f"Impossible d'ouvrir le fichier en écriture :\n{str(e)}\n\n"
                "Vérifiez que le fichier n'est pas déjà ouvert dans QGIS "
                "(retirez la couche du projet avant de renommer)."
            )
            return

        noms_appliques = []
        for i in range(self.table_bandes.rowCount()):
            nouveau_nom = self.table_bandes.item(i, 2).text().strip()
            if nouveau_nom:
                ds.GetRasterBand(i + 1).SetDescription(nouveau_nom)
                noms_appliques.append(nouveau_nom)

        ds.FlushCache()
        ds = None

        dossier = os.path.dirname(chemin)
        actions = "\n".join(
            [f"  - Bande {i+1} renommée en \"{nom}\"" for i, nom in enumerate(noms_appliques)]
        )
        self.ecrire_journal(
            dossier=dossier,
            objectif=f"Renommage des bandes de l'image {os.path.basename(chemin)} "
                     f"via le plugin Stack Bands S2",
            actions=actions,
            resultat=f"Noms de bandes mis à jour dans {chemin} : {', '.join(noms_appliques)}",
        )

        QMessageBox.information(
            self, "Succès", f"Les noms de bandes ont été enregistrés dans :\n{chemin}"
        )
