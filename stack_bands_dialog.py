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

        layout.addWidget(QLabel("Dossier de sortie :"))
        sortie_dossier_layout = QHBoxLayout()
        self.champ_dossier_sortie_stack = QLineEdit()
        bouton_parcourir_sortie_stack = QPushButton("Parcourir...")
        bouton_parcourir_sortie_stack.clicked.connect(self.choisir_dossier_sortie_stack)
        sortie_dossier_layout.addWidget(self.champ_dossier_sortie_stack)
        sortie_dossier_layout.addWidget(bouton_parcourir_sortie_stack)
        layout.addLayout(sortie_dossier_layout)

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
            if not self.champ_dossier_sortie_stack.text().strip():
                self.champ_dossier_sortie_stack.setText(dossier)

    def choisir_dossier_sortie_stack(self):
        dossier = QFileDialog.getExistingDirectory(self, "Choisir le dossier de sortie")
        if dossier:
            self.champ_dossier_sortie_stack.setText(dossier)

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
        dossier_sortie = self.champ_dossier_sortie_stack.text().strip() or dossier
        nom_sortie = self.champ_sortie.text().strip()

        if not dossier or not os.path.isdir(dossier):
            QMessageBox.warning(self, "Erreur", "Veuillez choisir un dossier valide.")
            return

        if not os.path.isdir(dossier_sortie):
            QMessageBox.warning(self, "Erreur", "Veuillez choisir un dossier de sortie valide.")
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

        fichier_sortie = os.path.join(dossier_sortie, nom_sortie)
        fichier_vrt = os.path.join(dossier_sortie, "_temp_stack.vrt")

        try:
            self.barre_progression.setValue(10)

            vrt_options = gdal.BuildVRTOptions(separate=True)
            vrt_ds = gdal.BuildVRT(fichier_vrt, chemins, options=vrt_options)
            vrt_ds = None
            self.barre_progression.setValue(40)

            translate_options = gdal.TranslateOptions(
                format="GTiff",
                creationOptions=["COMPRESS=DEFLATE", "TILED=YES"],
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
                dossier=dossier_sortie,
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

        layout.addWidget(QLabel(
            "Fichiers raster à traiter (.tif, .jp2) - sélection multiple possible :"
        ))
        fichier_layout = QHBoxLayout()
        bouton_parcourir_image = QPushButton("Choisir un ou plusieurs fichiers...")
        bouton_parcourir_image.clicked.connect(self.choisir_images_renommer)
        bouton_ajouter_dossier = QPushButton("Charger un dossier entier...")
        bouton_ajouter_dossier.clicked.connect(self.choisir_dossier_renommer)
        fichier_layout.addWidget(bouton_parcourir_image)
        fichier_layout.addWidget(bouton_ajouter_dossier)
        layout.addLayout(fichier_layout)

        layout.addWidget(QLabel(
            "Dossier de sortie (pour les copies renommées issues de .jp2 ; "
            "les .tif modifiés en place restent dans leur dossier d'origine) :"
        ))
        sortie_layout = QHBoxLayout()
        self.champ_dossier_sortie_renommer = QLineEdit()
        bouton_parcourir_sortie_renommer = QPushButton("Parcourir...")
        bouton_parcourir_sortie_renommer.clicked.connect(self.choisir_dossier_sortie_renommer)
        sortie_layout.addWidget(self.champ_dossier_sortie_renommer)
        sortie_layout.addWidget(bouton_parcourir_sortie_renommer)
        layout.addLayout(sortie_layout)

        layout.addWidget(QLabel(
            "Double-cliquez sur la colonne \"Nouveau nom\" pour modifier le nom de chaque bande "
            "(une ligne par bande, plusieurs bandes possibles si un fichier en contient plusieurs) :"
        ))
        self.table_bandes = QTableWidget(0, 4)
        self.table_bandes.setHorizontalHeaderLabels(["Fichier", "Bande", "Nom actuel", "Nouveau nom"])
        self.table_bandes.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_bandes.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_bandes.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_bandes.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.table_bandes)

        retirer_layout = QHBoxLayout()
        bouton_retirer_ligne = QPushButton("Retirer la sélection")
        bouton_retirer_ligne.clicked.connect(self.retirer_lignes_renommage)
        retirer_layout.addWidget(bouton_retirer_ligne)
        layout.addLayout(retirer_layout)

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

    def choisir_images_renommer(self):
        chemins, _ = QFileDialog.getOpenFileNames(
            self, "Choisir un ou plusieurs fichiers raster", "",
            "Rasters (*.tif *.tiff *.jp2);;GeoTIFF (*.tif *.tiff);;JPEG2000 (*.jp2);;Tous les fichiers (*)"
        )
        if chemins:
            for chemin in chemins:
                self.ajouter_fichier_a_la_table(chemin)
            if not self.champ_dossier_sortie_renommer.text().strip():
                self.champ_dossier_sortie_renommer.setText(os.path.dirname(chemins[0]))

    def choisir_dossier_sortie_renommer(self):
        dossier = QFileDialog.getExistingDirectory(self, "Choisir le dossier de sortie")
        if dossier:
            self.champ_dossier_sortie_renommer.setText(dossier)

    def choisir_dossier_renommer(self):
        dossier = QFileDialog.getExistingDirectory(self, "Choisir un dossier de bandes")
        if not dossier:
            return
        extensions = (".jp2", ".tif", ".tiff")
        fichiers = sorted([
            os.path.join(dossier, f) for f in os.listdir(dossier)
            if f.lower().endswith(extensions)
        ])
        for chemin in fichiers:
            self.ajouter_fichier_a_la_table(chemin)
        if fichiers and not self.champ_dossier_sortie_renommer.text().strip():
            self.champ_dossier_sortie_renommer.setText(dossier)

    def ajouter_fichier_a_la_table(self, chemin):
        try:
            ds = gdal.Open(chemin)
        except Exception:
            return
        if ds is None:
            return

        nb_bandes = ds.RasterCount
        for i in range(1, nb_bandes + 1):
            band = ds.GetRasterBand(i)
            nom_actuel = band.GetDescription() or "(sans nom)"

            ligne = self.table_bandes.rowCount()
            self.table_bandes.insertRow(ligne)

            item_fichier = QTableWidgetItem(os.path.basename(chemin))
            item_fichier.setFlags(item_fichier.flags() & ~Qt.ItemIsEditable)
            item_fichier.setData(Qt.UserRole, chemin)
            self.table_bandes.setItem(ligne, 0, item_fichier)

            item_bande = QTableWidgetItem(str(i))
            item_bande.setFlags(item_bande.flags() & ~Qt.ItemIsEditable)
            item_bande.setData(Qt.UserRole, i)
            self.table_bandes.setItem(ligne, 1, item_bande)

            item_actuel = QTableWidgetItem(nom_actuel)
            item_actuel.setFlags(item_actuel.flags() & ~Qt.ItemIsEditable)
            self.table_bandes.setItem(ligne, 2, item_actuel)

            nom_propose = self.extraire_nom_bande(os.path.basename(chemin))
            item_nouveau = QTableWidgetItem(nom_propose)
            self.table_bandes.setItem(ligne, 3, item_nouveau)

        ds = None

    def retirer_lignes_renommage(self):
        lignes_selectionnees = sorted(
            set(item.row() for item in self.table_bandes.selectedItems()),
            reverse=True,
        )
        if not lignes_selectionnees:
            QMessageBox.information(
                self, "Information",
                "Sélectionnez d'abord une ou plusieurs lignes à retirer."
            )
            return
        for ligne in lignes_selectionnees:
            self.table_bandes.removeRow(ligne)

    def enregistrer_noms_bandes(self):
        if self.table_bandes.rowCount() == 0:
            QMessageBox.warning(self, "Erreur", "Aucun fichier chargé.")
            return

        dossier_sortie = self.champ_dossier_sortie_renommer.text().strip()
        if not dossier_sortie or not os.path.isdir(dossier_sortie):
            QMessageBox.warning(
                self, "Erreur",
                "Veuillez choisir un dossier de sortie valide (utilisé pour les "
                "copies renommées issues des fichiers .jp2)."
            )
            return

        # Regrouper les lignes du tableau par fichier source
        fichiers = {}  # chemin -> {num_bande: nouveau_nom}
        for ligne in range(self.table_bandes.rowCount()):
            chemin = self.table_bandes.item(ligne, 0).data(Qt.UserRole)
            num_bande = self.table_bandes.item(ligne, 1).data(Qt.UserRole)
            nouveau_nom = self.table_bandes.item(ligne, 3).text().strip()
            fichiers.setdefault(chemin, {})[num_bande] = nouveau_nom

        resultats = []
        erreurs = []
        for chemin, noms_par_bande in fichiers.items():
            extension = os.path.splitext(chemin)[1].lower()
            try:
                if extension in (".tif", ".tiff"):
                    resultat = self._enregistrer_en_place(chemin, noms_par_bande)
                else:
                    resultat = self._enregistrer_via_copie(chemin, noms_par_bande, dossier_sortie)
                resultats.append(resultat)
            except Exception as e:
                erreurs.append(f"{os.path.basename(chemin)} : {str(e)}")

        message = f"{len(resultats)} fichier(s) traité(s) avec succès."
        if erreurs:
            message += "\n\nErreurs :\n" + "\n".join(erreurs)
            QMessageBox.warning(self, "Terminé avec erreurs", message)
        else:
            QMessageBox.information(self, "Succès", message)

    def _enregistrer_en_place(self, chemin, noms_par_bande):
        try:
            ds = gdal.Open(chemin, gdal.GA_Update)
        except Exception as e:
            raise Exception(
                f"Impossible d'ouvrir en écriture ({str(e)}). "
                "Retirez la couche du projet QGIS avant de renommer."
            )

        noms_appliques = []
        for num_bande, nom in noms_par_bande.items():
            if nom:
                ds.GetRasterBand(num_bande).SetDescription(nom)
                noms_appliques.append(nom)

        ds.FlushCache()
        ds = None

        self._journaliser_renommage(chemin, chemin, noms_appliques)
        return chemin

    def _enregistrer_via_copie(self, chemin, noms_par_bande, dossier_sortie):
        base = os.path.splitext(os.path.basename(chemin))[0]

        # Le fichier de sortie porte le nom de la bande elle-même (ex. B01.tif),
        # afin que le numéro de référence de la bande soit conservé et lisible
        # directement dans le nom de fichier, sans suffixe artificiel.
        noms_valides = [n for n in noms_par_bande.values() if n]
        if len(noms_valides) == 1:
            nom_fichier_sortie = f"{noms_valides[0]}.tif"
        elif len(noms_valides) > 1:
            nom_fichier_sortie = f"{'_'.join(noms_valides)}.tif"
        else:
            nom_fichier_sortie = f"{base}.tif"

        fichier_sortie = os.path.join(dossier_sortie, nom_fichier_sortie)

        translate_options = gdal.TranslateOptions(
            format="GTiff",
            creationOptions=["COMPRESS=DEFLATE", "TILED=YES"],
        )
        out_ds = gdal.Translate(fichier_sortie, chemin, options=translate_options)

        noms_appliques = []
        for num_bande, nom in noms_par_bande.items():
            if nom:
                out_ds.GetRasterBand(num_bande).SetDescription(nom)
                noms_appliques.append(nom)

        out_ds.FlushCache()
        out_ds = None

        nom_couche = noms_valides[0] if len(noms_valides) == 1 else os.path.splitext(nom_fichier_sortie)[0]
        couche = QgsRasterLayer(fichier_sortie, nom_couche)
        if couche.isValid():
            QgsProject.instance().addMapLayer(couche)

        self._journaliser_renommage(chemin, fichier_sortie, noms_appliques, dossier_sortie)
        return fichier_sortie

    def _journaliser_renommage(self, chemin_source, chemin_resultat, noms_appliques, dossier=None):
        dossier = dossier or os.path.dirname(chemin_source)
        actions = "\n".join(
            [f"  - Bande {i+1} renommée en \"{nom}\"" for i, nom in enumerate(noms_appliques)]
        )
        self.ecrire_journal(
            dossier=dossier,
            objectif=f"Renommage des bandes de l'image {os.path.basename(chemin_source)} "
                     f"via le plugin Stack Bands S2",
            actions=actions,
            resultat=f"Noms de bandes appliqués dans {chemin_resultat} : {', '.join(noms_appliques)}",
        )
